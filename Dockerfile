
FROM python:3.9.8-slim-bullseye

WORKDIR /root/project

RUN apt-get -y update  && apt-get -y upgrade

# Install make
RUN apt-get -y install make

RUN pip install pip-tools

COPY requirements.txt /tmp/requirements.txt

RUN pip install -r /tmp/requirements.txt

ENV PYTHONPATH "/root/project/"


ENTRYPOINT ["tail", "-f", "/dev/null"]