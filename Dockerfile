# pull official base image
FROM python:3.9.7

WORKDIR /usr/src/app
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN pip install --upgrade pip
COPY ./requirements.txt /usr/src/app/requirements.txt
RUN pip install -r requirements.txt

# copy project
COPY grafana_sync.py /usr/src/app/
CMD ["python", "grafana_sync.py"]
