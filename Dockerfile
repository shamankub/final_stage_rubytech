FROM python:3.9.7

WORKDIR /app

RUN apt-get update && apt-get install -y postgresql-client && apt-get install -y fonts-liberation && apt-get install -y rabbitmq-server && apt-get install -y tmux

RUN pip3 install --upgrade pip

COPY . .
RUN pip install -r requirements.txt

CMD sleep 10 && flask db init && flask db migrate && flask db upgrade && celery -A app.celery_app worker --detach --loglevel=info --beat && python app.py
