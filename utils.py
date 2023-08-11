import csv
import logging
import os
import threading
import zipfile
from functools import wraps
from io import BytesIO, TextIOWrapper
from logging.handlers import RotatingFileHandler
from typing import Union
from urllib.parse import urlparse

from flask import redirect, request, session, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from settings import LOGFILE_ABSOLUTE_PATH


def create_logger():
    """Функция для создания логгера."""

    # Отключение логирования стандартных сообщений Flask
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    # Создание логгера для приложения
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)

    # Создание объекта мьютекса
    log_lock = threading.Lock()

    # Конфигурация логирования и ротации лог-файлов при достижении размера 1 Mb
    with log_lock:
        if LOGFILE_ABSOLUTE_PATH:
            home_directory = os.getenv("HOME")
            log_file = os.path.join(home_directory, "logs", "history.log")
            file_handler = RotatingFileHandler(
                log_file, maxBytes=10**6, backupCount=5
            )
        else:
            file_handler = RotatingFileHandler(
                "history.log", maxBytes=10**6, backupCount=5
            )
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)

        # Добавление обработчика файла к логгеру приложения
        logger.addHandler(file_handler)

    return logger


# Создаем логгер
logger = create_logger()


def is_valid_url(url: str) -> bool:
    """Функция для проверки является ли строка ссылкой."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def unzip_and_parse_csv() -> Union[bool, list]:
    """Функция для распаковки ZIP-архива и создания из CSV-файла списка ссылок."""
    zip_file = request.files.get("file")
    if not zip_file or not zip_file.filename.lower().endswith(".zip"):
        logger.error("ZIP-архив не найден")
        return False

    try:
        # Извлечение CSV-файла из ZIP-архива
        with zipfile.ZipFile(zip_file) as archive:
            csv_files = [f for f in archive.namelist() if f.lower().endswith(".csv")]
            if not csv_files:
                logger.error("CSV-файл в ZIP-архиве не найден")
                return False
            csv_file = csv_files[0]
            with archive.open(csv_file) as file:
                # Чтение CSV-файла и извлечение ссылок
                csv_reader = csv.reader(TextIOWrapper(file, "utf-8"))
                url_list = []
                for row in csv_reader:
                    if len(row) > 0:
                        url_list.append(row[0])

        return url_list

    except zipfile.BadZipFile:
        logger.error("Загруженный файл не является ZIP-архивом или архив битый")
        return False


def read_log_file():
    """Функция для чтения лог-файла и возврата его содержимого."""
    with open("history.log", "r") as file:
        log_content = file.read()  # .splitlines()
    return log_content


def generate_pdf():
    """Функция для генерации PDF-файла с содержимым лог-файла."""
    buffer = BytesIO()

    # Загрузка шрифта с поддержкой русского языка
    pdfmetrics.registerFont(TTFont("Liberation", "LiberationSans-Regular.ttf"))

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=15,
        rightMargin=15,
        topMargin=20,
        bottomMargin=20,
    )
    story = []

    log_content = read_log_file()
    paragraphs = log_content.splitlines()

    # Создание стиля для текста с переносом строк
    style = ParagraphStyle("ParagraphWithLineBreaks")
    style.fontName = "Liberation"
    style.fontSize = 8
    style.textColor = colors.black
    style.keepWithNext = True

    # Добавление текста в документ с переносом строк
    for paragraph_text in paragraphs:
        paragraph = Paragraph(paragraph_text, style)
        story.append(paragraph)
        story.append(Spacer(1, 6))

    doc.build(story)

    buffer.seek(0)

    return buffer


def login_required(func):
    """Декоратор для проверки авторизации."""
    @wraps(func)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return decorated
