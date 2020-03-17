from altertech/pytpl:17
RUN /opt/venv/bin/pip3 install pytest PyMySQL
COPY ./etc/supervisor/conf.d/roboger.conf /etc/supervisor/conf.d/
RUN /opt/venv/bin/pip3 install --no-cache-dir robogerctl==2.0.5
RUN /opt/venv/bin/pip3 install --no-cache-dir roboger==2.0.13
ARG CACHEBUST=1
RUN curl https://raw.githubusercontent.com/alttch/roboger/master/tests/test.py -o /usr/local/roboger-test.py
