from altertech/pytpl:17
RUN /opt/venv/bin/pip3 install pytest PyMySQL
COPY ./etc/supervisor/conf.d/roboger.conf /etc/supervisor/conf.d/
RUN /opt/venv/bin/pip3 install --no-cache-dir robogerctl==2.0.5
RUN /opt/venv/bin/pip3 install --no-cache-dir roboger==2.0.14
RUN ln -sf /opt/venv/bin/robogerctl /usr/local/bin/robogerctl
ARG CACHEBUST=1
COPY ./tests/test.py /usr/local/roboger-test.py
