FROM tiangolo/uwsgi-nginx-flask:python3.6

COPY requirements.txt /tmp/


RUN    apt-get update -yqq \
    && apt-get upgrade -yqq \
    && apt-get install -yqq --no-install-recommends \
    && pip install -U pip && pip install -r /tmp/requirements.txt

# Downloading gcloud package
#RUN curl https://dl.google.com/dl/cloudsdk/release/google-cloud-sdk.tar.gz > /tmp/google-cloud-sdk.tar.gz
#RUN curl -sSL https://sdk.cloud.google.com | bash

#ENV PATH $PATH:/root/google-cloud-sdk/bin

RUN yes Y | apt-get install ca-certificates

RUN curl -sSL https://sdk.cloud.google.com | bash

ENV PATH $PATH:/root/google-cloud-sdk/bin

COPY ./app /app

COPY creds.json /app/

RUN gcloud auth activate-service-account --key-file=/app/creds.json \
           && gsutil cp gs://biotech_lee/keyword_extractor/module/keyword_extractor.py /app/keyword_extractor

#ENV PATH $PATH:/usr/local/gcloud/google-cloud-sdk/bin

ENV GOOGLE_APPLICATION_CREDENTIALS=/app/creds.json


ENV NGINX_WORKER_PROCESSES auto