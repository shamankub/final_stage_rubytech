import asyncio
import base64
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from math import ceil
from urllib.parse import parse_qs, urlparse

import aiohttp
import requests
from kombu import serialization
from celery import Celery
from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from PIL import Image

from settings import LOG_FILE_LENGTH, MONITORING_PERIOD, TIMEOUT, UNAVAILABILITY_PERIOD
from utils import generate_pdf, is_valid_url, logger, read_log_file, unzip_and_parse_csv

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://admin:admin@db:5432/mydatabase"
#app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///resources.db"
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Конфигурация Celery
# celery -A app.celery_app worker --loglevel=info --beat
# celery -A app.celery_app beat stop
# celery -A app.celery_app beat stop --pidfile= --force
app.config["CELERY_BROKER_URL"] = "amqp://guest@localhost//"
app.config["result_backend"] = "rpc://"

celery_app = Celery(app.name, broker=app.config["CELERY_BROKER_URL"])
celery_app.conf.update(app.config)

celery_app.conf.task_serializer = 'pickle'
celery_app.conf.result_serializer = 'pickle'
celery_app.conf.accept_content = ['pickle']

# Настраиваем сериализацию для Celery
serialization.register_pickle()

period_of_unavailability = timedelta(hours=UNAVAILABILITY_PERIOD)

celery_app.conf.beat_schedule = {
    "check-resources": {
        "task": "app.check_resource_availability",
        "schedule": timedelta(minutes=MONITORING_PERIOD),
    },
}


class WebResource(db.Model):
    """Модель для хранения информации о веб-ресурсе."""

    uuid = db.Column(
        db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True
    )
    url = db.Column(db.String(200), nullable=False)
    protocol = db.Column(db.String(10))
    domain = db.Column(db.String(100))
    domain_zone = db.Column(db.String(10))
    params = db.Column(db.JSON)
    path = db.Column(db.String(100))
    status_code = db.Column(db.Integer, default=200)
    is_available = db.Column(db.Boolean, default=True)
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    screenshot = db.Column(db.LargeBinary)

    def __repr__(self):
        return f"<WebResource {self.url}>"


class NewsFeed(db.Model):
    """Модель для хранения новостей, связанных с веб-ресурсами."""

    id = db.Column(db.Integer, primary_key=True)
    resource_id = db.Column(db.String(36))
    action = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<NewsFeed {self.id}>"


def add_news_in_feed(action, resource_id=None):
    """Функция для добавления событий в базу данных."""
    news_feed = NewsFeed(action=action, resource_id=resource_id)
    db.session.add(news_feed)
    db.session.commit()


# Реализация API-интерфейса
async def process_url(url):
    """Функция для обработки одной ссылки."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=TIMEOUT) as response:
                status_code = response.status

                # Разделение ссылки на протокол, домен, доменную зону и путь
                parsed_url = urlparse(url)
                protocol = parsed_url.scheme
                domain = parsed_url.netloc
                domain_zone = domain.split(".")[-1]
                path = parsed_url.path
                is_available = True if status_code < 400 else False

                # Преобразование параметров ссылки в словарь
                params = parse_qs(parsed_url.query)

                # Сохранение данных в базе данных
                resource = WebResource(
                    url=url,
                    protocol=protocol,
                    domain=domain,
                    domain_zone=domain_zone,
                    path=path,
                    params=params,
                    status_code=status_code,
                    is_available=is_available,
                )
                db.session.add(resource)
                db.session.commit()

                # Формирование JSON-ответа
                response_data = {
                    "url": url,
                    "protocol": protocol,
                    "domain": domain,
                    "domain_zone": domain_zone,
                    "path": path,
                    "params": params,
                    "status": status_code,
                }
                action = f"URL сохранён в базу данных: {url}"
                add_news_in_feed(action)
                logger.info(action)

                return response_data

    except aiohttp.ClientError:
        if not is_valid_url(url):
            action = f"URL не сохранён. '{url}' - не является ссылкой"
            add_news_in_feed(action)
            logger.error(action)
            return {"error": f"'{url}' - is not a link"}
        action = f"URL не сохранён. '{url}' - неправильная ссылка"
        add_news_in_feed(action)
        logger.error(action)
        return {"error": f"'{url}' - invalid link"}
    except asyncio.TimeoutError:
        action = f"URL не сохранён. '{url}' - время ожидания превышено"
        add_news_in_feed(action)
        logger.error(action)
        return {"error": f"'{url}' - timeout exceeded"}


@app.route("/add_resource_via_form", methods=["POST"])
@app.route("/resources", methods=["POST"])
async def process_resource():
    """Функция для обработки POST-запроса со ссылкой на веб-ресурс."""
    path = request.path
    zip_file = request.files.get("file")
    if zip_file:
        csv_in_request = unzip_and_parse_csv()
        if isinstance(csv_in_request, list):
            url_list = csv_in_request
        elif isinstance(csv_in_request, bool):
            action = "Ошибка при обработке ZIP-файла"
            add_news_in_feed(action)
            logger.error(action)
            # Определение роута, через который перешли в функцию
            if path == "/add_resource_via_form":
                return redirect(url_for("render_resources"))
            elif path == "/resources":
                return {"error": "Error processing ZIP-file"}
    else:
        url = request.form.get("single_url")
        url_list = [url]

    # Инициализация счетчиков
    total_urls = len(url_list)
    processed_urls = 0
    db_saved_urls = 0
    errors = 0

    # Асинхронная обработка ссылок
    results = await asyncio.gather(*[process_url(url) for url in url_list])

    for result in results:
        if result.get("error"):
            errors += 1
        else:
            db_saved_urls += 1

        # Логирование результата опроса статус кода сайта
        if result.get("url"):
            action = f"Опрос статус кода URL: {result.get('url')}, Status Code: {result.get('status')}"
            add_news_in_feed(action)
            logger.info(action)

    processed_urls = len(results)

    status = {
        "total_urls": total_urls,
        "processed_urls": processed_urls,
        "errors": errors,
        "db_saved_urls": db_saved_urls,
    }

    # Логирование итогов опроса
    action = f"Статус обработки URL - Всего: {total_urls}, Обработано: {processed_urls}, Ошибок: {errors}, Сохранено: {db_saved_urls}"
    add_news_in_feed(action)
    logger.info(action)

    # Формирование JSON-ответа
    response_data = {
        "status": status,
        "results": results,
    }

    # Определение роута, через который перешли в функцию
    if path == "/add_resource_via_form":
        return redirect(url_for("render_resources"))
    elif path == "/resources":
        return jsonify(response_data)


@app.route("/resource/<string:resource_id>/upload_screenshot", methods=["POST"])
def upload_screenshot(resource_id):
    """Функция для обработки POST-запроса со скриншотом и UUID веб-ресурса."""
    screenshot_data = request.files.get("screenshot")

    # Проверка наличия ресурса в базе данных
    resource = WebResource.query.get(resource_id)
    if not resource:
        action = f"Невозможно загрузить скриншот. Ресурс не найден. ID: {resource_id}"
        add_news_in_feed(action, resource_id)
        logger.error(action)
        return jsonify(
            {"error": "Unable to upload screenshot because resource not found"}
        )

    # Проверка наличия скриншота в запросе
    if not screenshot_data:
        action = "Данные скриншота не получены"
        add_news_in_feed(action, resource_id)
        logger.error(action)
        return jsonify({"error": "No screenshot data"})

    try:
        # Чтение и обработка изображения
        img = Image.open(screenshot_data)
        # Масштабирование изображения до максимальных размеров 500x500 пикселей
        img.thumbnail((500, 500))

        # Кодирование изображения в формат base64
        img_buffer = BytesIO()
        img.save(img_buffer, format="PNG")
        screenshot_base64 = base64.b64encode(img_buffer.getvalue()).decode("utf-8")
        screenshot_bytes = base64.b64decode(screenshot_base64)

        # Сохранение скриншота в базе данных
        resource.screenshot = screenshot_bytes
        # resource.screenshot = screenshot_base64
        db.session.commit()

        action = f"Скриншот сохранен для ресурса с ID: {resource_id}"
        add_news_in_feed(action, resource_id)
        logger.info(action)
        return redirect(f"/resources/{resource_id}")
    except Exception as e:
        action = f"Ошибка обработки скриншота: {e}"
        add_news_in_feed(action, resource_id)
        logger.error(action)
        return redirect(f"/resources/{resource_id}")


@app.route("/resources", methods=["GET"])
def get_resources():
    """Функция для обработки GET-запроса с параметрами для получения ссылок на
    веб-ресурсы из базы данных с возможностью фильтрации и пагинации."""

    # Получение параметров запроса
    domain = request.args.get("domain")
    domain_zone = request.args.get("domain_zone")
    uuid = request.args.get("uuid")
    is_available = request.args.get("is_available")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 10))

    # Формирование базового запроса
    query = WebResource.query

    # Добавление фильтров к базовому запросу
    if domain:
        query = query.filter(WebResource.domain.ilike(f"%{domain}%"))
    if domain_zone:
        query = query.filter_by(domain_zone=domain_zone)
    if uuid:
        query = query.filter_by(uuid=uuid)
    if is_available:
        query = query.filter_by(is_available=is_available)

    # Получение общего количества записей
    total_count = query.count()

    # Применение пагинации
    query = query.offset((page - 1) * per_page).limit(per_page)

    # Получение результатов
    resources = query.all()

    # Формирование JSON-ответа
    response_data = {
        "total_count": total_count,
        "page": page,
        "per_page": per_page,
        "resources": [
            {
                "url": resource.url,
                "status_code": resource.status_code,
            }
            for resource in resources
        ],
        "prev_page": url_for(
            "get_resources",
            domain=domain,
            domain_zone=domain_zone,
            is_available=is_available,
            page=page - 1,
        )
        if page > 1
        else None,
        "next_page": url_for(
            "get_resources",
            domain=domain,
            domain_zone=domain_zone,
            is_available=is_available,
            page=page + 1,
        )
        if total_count > page * per_page
        else None,
    }

    return jsonify(response_data)


@app.route("/sliced_log", methods=["GET"])
def get_sliced_log():
    """Функция для вывода последних 50 строчек из лог-файла."""
    log_lines = []

    with open("history.log", "r") as log_file:
        log_lines = log_file.readlines()

    return "<br>".join(log_lines[-LOG_FILE_LENGTH:])


# Реализация веб-интерфейса
@app.route("/add_resource", methods=["GET"])
def add_resource():
    """Функция для добавления веб-ресурса."""
    return render_template("add_resource.html")


@app.route("/", methods=["GET"])
@app.route("/resources_list", methods=["GET"])
def render_resources():
    """Функция для вывода таблицы всех веб-ресурсов с пагинацией и фильтрацией."""
    domain = request.args.get("domain")
    domain_zone = request.args.get("domain_zone")
    is_available = request.args.get("is_available")
    zone_list = db.session.query(WebResource.domain_zone).distinct().all()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 10))

    query = WebResource.query

    if domain:
        query = query.filter(WebResource.domain.contains(domain))
    if domain_zone:
        query = query.filter_by(domain_zone=domain_zone)
    if is_available:
        query = query.filter_by(is_available=is_available)

    total_count = query.count()

    total_pages = ceil(total_count / per_page)

    query = query.offset((page - 1) * per_page).limit(per_page)

    resources = query.all()

    return render_template(
        "resources_list.html",
        resources=resources,
        zone_list=zone_list,
        prev_page=page - 1 if page > 1 else None,
        next_page=page + 1 if total_count > page * per_page else None,
        current_page=page,
        total_pages=total_pages,
    )


@app.route("/log")
def log_page():
    """Функция для отображения страницы, выводящей строки из лог-файла."""
    log_content = read_log_file()
    return render_template("log.html", log_content=log_content)


@app.route("/download_log")
def download_log():
    """Функция для скачивания лог-файла в формате PDF."""
    pdf_buffer = generate_pdf()

    response = make_response(pdf_buffer.getvalue())
    response.headers.set("Content-Disposition", "attachment", filename="history.pdf")
    response.headers.set("Content-Type", "application/pdf")

    return response


@app.route("/news_feed")
def news_feed():
    """Функция для вывода всех событий на страницу Лента новостей."""
    news = NewsFeed.query.all()
    return render_template("news_feed.html", news=news)


@app.route("/resources/<string:resource_id>", methods=["GET"])
def render_resource(resource_id):
    """Функция для вывода всех данных веб-ресурса."""
    resource = WebResource.query.get(resource_id)

    if not resource:
        action = f"Невозможно отрендерить шаблон. Ресурс не найден. ID: {resource_id}"
        add_news_in_feed(action, resource_id)
        logger.error(action)
        return jsonify(
            {"error": "Unable to render template because resource not found"}
        )

    # Получение данных из модели NewsFeed
    news_feed_data = NewsFeed.query.filter_by(resource_id=resource_id).all()
    actions = [news_feed.action for news_feed in news_feed_data]

    # Получение изображения (если есть) для веб-ресурса
    image_data = None
    if resource.screenshot:
        image_data = base64.b64encode(resource.screenshot).decode("utf-8")

    return render_template(
        "resource_detail.html",
        resource=resource,
        image_data=image_data,
        actions=actions,
    )


@app.route("/resources/<string:resource_id>", methods=["POST"])
def delete_resource(resource_id):
    """Функция для удаления веб-ресурса."""
    resource = WebResource.query.get(resource_id)
    if not resource:
        # Логирование ошибки при удалении веб-ресурса
        action = f"Не удалось удалить ресурс. Ресурс не найден. ID: {resource_id}"
        add_news_in_feed(action, resource_id)
        logger.error(action)
        return jsonify({"error": "Resource not found"})

    db.session.delete(resource)
    db.session.commit()

    action = f"Ресурс удалён. ID: {resource_id}"
    add_news_in_feed(action, resource_id)
    logger.info(action)
    return redirect(url_for("render_resources"))


@app.route("/about")
def about():
    """Функция для рендеринга страницы О проекте."""
    return render_template("about.html")


# Определение задач для планировщика
@celery_app.task
def check_single_resource(resource):
    """Функция проверки доступности единичного веб-ресурса."""
    with app.app_context():
        try:
            response = requests.get(resource.url, timeout=TIMEOUT)
            status_code = response.status_code
            last_checked = datetime.now()
            is_available = status_code == 200
            if resource.is_available is False and is_available:
                logger.info(f"Веб-ресурс стал недоступен: {resource.url}")
            elif resource.is_available and is_available is False:
                logger.info(f"Веб-ресурс снова доступен: {resource.url}")
            if is_available:
                resource.last_checked = last_checked
            else:
                if last_checked - resource.last_checked > period_of_unavailability:
                    resource.is_active = False
                    logger.info(f"Прекращение мониторинга веб-ресурса: {resource.url}")
            resource.is_available = is_available
            db.session.add(resource)
            db.session.commit()
        except requests.exceptions.RequestException:
            resource.is_available = False
            if datetime.now() - resource.last_checked > period_of_unavailability:
                resource.is_active = False
            db.session.add(resource)
            db.session.commit()


@celery_app.task
def check_resource_availability():
    """Функция для проверки доступности всех активных веб-ресурсов."""
    resources = get_active_resources()
    tasks = []
    for resource in resources:
        task = check_single_resource.apply_async(args=(resource,))
        tasks.append(task)
    return tasks


def get_active_resources():
    """Функция для получения активных ресурсов из базы данных."""
    with app.app_context():
        active_resources = WebResource.query.filter_by(is_active=True).all()
    return active_resources


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
