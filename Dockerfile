FROM ubuntu
# prepare system
RUN apt-get update && apt-get -y upgrade && apt-get -y dist-upgrade
RUN env DEBIAN_FRONTEND=noninteractive apt-get install -y tzdata
RUN ln -sf /usr/share/zoneinfo/Etc/UTC /etc/localtime
RUN apt-get -y install curl python3 python3-pip python3-cryptography python-pip jq vim-tiny iproute2 net-tools psmisc supervisor sqlite3 coreutils python3-pandas
RUN apt-get -y clean
RUN pip install superlance
RUN mkdir /opt/roboger
COPY bin/ /opt/roboger/bin/
COPY etc/roboger.ini-dist /opt/roboger/
COPY lib/ /opt/roboger/lib/
COPY sbin/ /opt/roboger/sbin/
COPY LICENSE /opt/roboger/
COPY README.md /opt/roboger/
COPY roboger-sqlite.sql /opt/roboger
COPY install.sh /opt/roboger/
COPY etc/supervisor/conf.d/roboger.conf /etc/supervisor/conf.d/
# install
RUN cd /opt/roboger && /opt/roboger/install.sh
RUN cp /opt/roboger/var/db/roboger.db /opt/roboger/roboger.init.db
# copy dstart
COPY docker-start.sh /start
EXPOSE 7719
CMD [ "/bin/bash", "/start" ]
