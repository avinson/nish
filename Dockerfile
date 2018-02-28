FROM python:2.7-slim-jessie

RUN apt-get -qy update && apt-get install -qy build-essential git libmagic-dev wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV DOCKERIZE_VERSION 0.6.0
ENV DOCKERIZE_URL https://github.com/jwilder/dockerize/releases/download/v${DOCKERIZE_VERSION}/dockerize-linux-amd64-v${DOCKERIZE_VERSION}.tar.gz
RUN wget -O /tmp/dockerize.tgz --quiet $DOCKERIZE_URL && ( cd /usr/bin && tar xzf /tmp/dockerize.tgz )

ENV SUPOYBOT_VERSION 0.83.4.1
RUN git clone https://github.com/Supybot/Supybot.git && cd Supybot && git checkout -b v${SUPYBOT_VERSION} && python ./setup.py install && rm -rf /Supybot

RUN useradd -d /app -m -r -s /usr/sbin/nologin -U supybot -u 1001

COPY . /app/
WORKDIR /app
RUN pip install -r requirements.txt
RUN chown -R 1001 /app

USER supybot
RUN mkdir -p backup data logs
ENTRYPOINT /app/docker-entrypoint.sh
