import csv
import zipfile
from urllib.parse import urlencode

from faker import Faker

fake = Faker()
csv_to_zip = "links.csv"
zip_file = "links.zip"


def generate_link() -> str:
    """Функция для генерации фейковой ссылки (URL), ссылки с параметрами
    или не ссылки (URI)."""
    if fake.boolean(chance_of_getting_true=90):
        link = fake.url()
        if i % 2 == 0:
            params = {fake.word(): fake.word(), fake.word(): fake.word()}
            query_string = urlencode(params)
            link = f"{link}?{query_string}"
    else:
        domain = fake.domain_name()
        path = fake.uri_path()
        params = {fake.word(): fake.word(), fake.word(): fake.word()}
        query_string = urlencode(params)
        link = f"http://{domain}{path}?{query_string}"

    return link


# Создание CSV-файла с фейковыми ссылками
with open(csv_to_zip, "w", newline="") as csvfile:
    writer = csv.writer(csvfile)

    for i in range(100):
        link = generate_link()
        writer.writerow([link])

# Упаковка CSV-файла в ZIP-архив
with zipfile.ZipFile(zip_file, "w") as zipf:
    zipf.write(csv_to_zip)

print(f"Файл {csv_to_zip} успешно создан и упакован в {zip_file}!")
