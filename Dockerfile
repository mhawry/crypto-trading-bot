FROM python:3.8-slim-buster

WORKDIR /usr/src/app

COPY requirements.txt /tmp/
RUN pip install --requirement /tmp/requirements.txt

COPY . .

CMD ["python", "./main.py"]
