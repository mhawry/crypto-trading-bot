FROM python:3.10-slim-buster

WORKDIR /usr/src/app

COPY requirements.txt /tmp/
RUN pip install --requirement /tmp/requirements.txt --root-user-action=ignore

COPY . .

CMD ["python", "./main.py"]
