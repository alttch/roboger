from altertech/pytpl:32
RUN /opt/venv/bin/pip3 install pytest PyMySQL
COPY ./etc/supervisor/conf.d/roboger.conf /etc/supervisor/conf.d/
RUN /opt/venv/bin/pip3 install --no-cache-dir robogerctl==2.0.14
RUN /opt/venv/bin/pip3 install --no-cache-dir roboger==2.0.27
COPY ./bin/robogerctl-docker /usr/bin/robogerctl
COPY ./tests/test.py /usr/local/roboger-test.py
