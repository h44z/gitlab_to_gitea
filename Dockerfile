FROM python:3.6-alpine


RUN apk --update add git

WORKDIR /app
ADD requirements.txt .
RUN python3 -m pip install -r requirements.txt

