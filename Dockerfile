FROM ubuntu
# prepare system
RUN apt-get update && apt-get -y upgrade && apt-get -y dist-upgrade
RUN env DEBIAN_FRONTEND=noninteractive apt-get install -y tzdata
RUN ln -sf /usr/share/zoneinfo/Etc/UTC /etc/localtime
RUN apt-get -y install --no-install-recommends curl
RUN apt-get -y install --no-install-recommends python3
RUN apt-get -y install --no-install-recommends python3-pip
RUN apt-get -y install --no-install-recommends python3-cryptography
RUN apt-get -y install --no-install-recommends python-pip
RUN apt-get -y install --no-install-recommends jq
RUN apt-get -y install --no-install-recommends vim-tiny
RUN apt-get -y install --no-install-recommends iproute2
RUN apt-get -y install --no-install-recommends net-tools
RUN apt-get -y install --no-install-recommends supervisor
RUN apt-get -y install --no-install-recommends sqlite3
RUN apt-get -y install --no-install-recommends coreutils
RUN apt-get -y install --no-install-recommends python3-dev
RUN apt-get -y install --no-install-recommends python3-wheel
RUN apt-get -y install --no-install-recommends python3-setuptools
RUN apt-get -y clean
RUN pip install superlance
RUN mkdir /opt/roboger
COPY bin/ /opt/roboger/bin/
COPY lib/ /opt/roboger/lib/
COPY sbin/ /opt/roboger/sbin/
COPY LICENSE /opt/roboger/
COPY roboger-sqlite.sql /opt/roboger
COPY install.sh /opt/roboger/
COPY etc/supervisor/conf.d/roboger.conf /etc/supervisor/conf.d/
RUN sed -i 's/^\(\[program:roboger\]\)/\1\nstdout_logfile=\/dev\/stdout\nstdout_logfile_maxbytes=0\nstderr_logfile=\/dev\/stderr\nstderr_logfile_maxbytes=0/g' /etc/supervisor/conf.d/roboger.conf
COPY etc/roboger.ini-dist /opt/roboger/
# install
RUN cd /opt/roboger && /opt/roboger/install.sh
RUN cp /opt/roboger/var/db/roboger.db /opt/roboger/roboger.init.db
RUN ln -sf /opt/roboger/bin/roboger-cmd /usr/local/bin/roboger-cmd
# copy dstart
COPY docker-start.sh /start
EXPOSE 7719
CMD [ "/bin/bash", "/start" ]
