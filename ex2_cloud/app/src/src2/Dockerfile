FROM ubuntu:18.04
ARG ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y 
RUN apt-get install -y python3-pip python3-dev 
RUN apt update
RUN DEBIAN_FRONTEND=noninteractive apt-get install curl -y
RUN apt install sudo
RUN DEBIAN_FRONTEND=noninteractive apt-get install zip -y
RUN DEBIAN_FRONTEND=noninteractive apt-get install unzip -y

COPY requirements.txt /app/requirements.txt

WORKDIR /app

RUN pip3 install pika && \
    pip3 install -r requirements.txt

RUN pip3 install --upgrade awscli

COPY app01.py /app/

ENTRYPOINT [ "python3" ]

CMD [ "app01.py" ]
