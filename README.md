## Финальное тестовое задание для голодных игр

### Стек

`Python` 3.9

`Flask` 2.2.3

`Celery`

`asyncio`

`aiohttp`

`SQLAlchemy`

`PostgreSQL` 14.7

`Pillow`

### Инструкция по запуску проекта:

Чтобы запустить проект, достаточно воспользоваться командой `docker-compose up`, находясь в директории с проектом.

После создания и запуска контейнера можно переходить по адресу `http://localhost/`

Также в директории с проектом есть файл `links.zip`, с помощью которого можно наполнить базу данных

Для этого нужно в шапке сайте перейти `Добавить ресурс` -> `Файл` -> `Загрузить ZIP-архив`

Также в шапке есть ссылки для перехода на `список всех ресурсов`, `ленту новостей`, `текст из лог-файла`, `страничку о проекте`

Из списка всех ресурсов можно перейти на страницу отдельного ресурса, нажав на него.

На странице веб-ресурса выводятся разложенные данные по ресурсу, кнопка добавления или изменения скриншота и лента новостей. 

### Список файлов:
1. `app.py` - главный файл проекта
2. `settings.py` - файл конфигурации
3. `make_zipfile.py` - модуль для создания zip-файла links.zip
4. `utils.py` - модуль со вспомогательными функциями
5. `requirements.txt` - файл зависимостей
6. `links.zip` - zip-архив с csv-файлом

### Описание всех эндпоинтов:

#### 1. process_resource()

Метод: POST

Маршрут: `/add_resource_via_form`, `/resources`

Описание: Функция для обработки POST-запроса со ссылкой на веб-ресурс. Принимает ссылку на ресурс в теле запроса или в форме отправки, либо список ссылок из ZIP-файла. Асинхронно обрабатывает каждую ссылку с помощью функции process_url(). Сохраняет информацию о ресурсах в базе данных и формирует JSON-ответ с информацией о статусе обработки ссылок.

Возвращаемое значение: JSON-ответ с информацией о статусе обработки ссылок.

#### 2. process_url(url)

Асинхронная функция

Описание: Функция для обработки одной ссылки. Проверяет доступность ссылки, получает ее статус код, разделяет ссылку на протокол, домен, доменную зону и путь, преобразует параметры ссылки в словарь. Сохраняет данные о ресурсе в базе данных. Формирует JSON-ответ с информацией о ресурсе.

Возвращаемое значение: JSON-ответ с информацией о ресурсе или ошибкой, если ссылка некорректна или время ожидания превышено.

#### 3. upload_screenshot(resource_id)

Метод: POST

Маршрут: `/resource/<string:resource_id>/upload_screenshot`

Описание: Функция для обработки POST-запроса со скриншотом и UUID веб-ресурса. Получает файл скриншота и UUID ресурса. Проверяет наличие ресурса в базе данных. Если ресурс найден, обрабатывает изображение, сохраняет его в базе данных и возвращает успешный ответ. В противном случае, возвращает ошибку.

Возвращаемое значение: Редирект или JSON-ответ в зависимости от результата операции.

#### 4. get_resources()

Метод: GET

Маршрут: `/resources`

Описание: Функция для обработки GET-запроса с параметрами для получения ссылок на веб-ресурсы из базы данных с возможностью фильтрации и пагинации. Получает параметры запроса: domain, domain_zone, uuid, is_available, page, per_page. Формирует базовый запрос на основе параметров. Получает общее количество записей и применяет пагинацию к запросу. Получает результаты запроса и формирует JSON-ответ с информацией о ресурсах и пагинации.

Возвращаемое значение: JSON-ответ с информацией о ресурсах и пагинации.

#### 5. get_sliced_log()

Метод: GET

Маршрут: `/sliced_log`

Описание: Функция для вывода последних 50 строк из лог-файла.

Возвращаемое значение: HTML-строка, содержащая последние 50 строк из лог-файла.

#### 6. add_resource()

Метод: GET

Маршрут: `/add_resource`

Описание: Функция для добавления веб-ресурса.

Возвращаемое значение: Отображение шаблона "add_resource.html".

#### 7. render_resources()

Метод: GET

Маршрут: `/`, `/resources_list`

Описание: Функция для вывода таблицы всех веб-ресурсов с пагинацией и фильтрацией. Принимает параметры фильтрации (domain, domain_zone, is_available) из строки запроса. Выполняет запрос к базе данных, фильтруя ресурсы по указанным параметрам и применяя пагинацию.

Возвращаемое значение: Отображение шаблона "resources_list.html".

#### 8. log_page()

Метод: GET

Маршрут: `/log`

Описание: Функция для отображения страницы, выводящей строки из лог-файла.

Возвращаемое значение: Отображение шаблона "log.html" с содержимым лог-файла.

#### 9. download_log()

Метод: GET

Маршрут: `/download_log`

Описание: Функция для скачивания лог-файла в формате PDF.

Возвращаемое значение: Файл PDF, содержащий содержимое лог-файла.

#### 10. news_feed()

Метод: GET

Маршрут: `/news_feed`

Описание: Функция для вывода всех событий на страницу "Лента новостей". Извлекает все записи из таблицы NewsFeed в базе данных и передает их в шаблон "news_feed.html" для отображения.

Возвращаемое значение: Отображение шаблона "news_feed.html" с данными о новостях.

#### 11. render_resource(resource_id)

Метод: GET

Маршрут: `/resources/<string:resource_id>`

Описание: Функция для вывода всех данных веб-ресурса с заданным resource_id. Извлекает данные о ресурсе из базы данных по указанному идентификатору и передает их в шаблон "resource_detail.html" для отображения. Также извлекает данные из модели NewsFeed и изображение ресурса, если они доступны.

Возвращаемое значение: Отображение шаблона "resource_detail.html" с данными о ресурсе.

#### 12. delete_resource(resource_id)

Метод: POST

Маршрут: `/resources/<string:resource_id>`

Описание: Функция для удаления веб-ресурса с заданным resource_id. Извлекает ресурс из базы данных по указанному идентификатору и удаляет его. Затем перенаправляет пользователя на страницу с таблицей всех ресурсов.

Возвращаемое значение: Перенаправление пользователя на страницу с таблицей всех ресурсов.

#### 13. about()

Метод: GET

Маршрут: `/about`

Описание: Функция для отображения страницы "О проекте".

Возвращаемое значение: Отображение шаблона "about.html".

### Celery (планировщик задач)
Код содержит две задачи Celery и несколько вспомогательных функций.

1. check_single_resource(resource)

Эта задача проверяет доступность одного веб-ресурса. Она отправляет GET-запрос по указанному URL, проверяет статус код ответа и обновляет информацию о доступности ресурса в базе данных.

2. check_resource_availability()

Эта задача проверяет доступность всех активных веб-ресурсов. Она получает список активных ресурсов из базы данных и для каждого ресурса запускает задачу check_single_resource асинхронно.

3. get_active_resources()

Вспомогательная функция, которая получает список активных ресурсов из базы данных.

В целом, код использует Celery для асинхронной проверки доступности веб-ресурсов и обновления информации о них в базе данных.
