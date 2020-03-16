from altertech/pytpl:13
RUN /opt/venv/bin/pip3 install pytest PyMySQL
RUN /opt/venv/bin/pip3 install robogerctl
RUN /opt/venv/bin/pip3 install roboger
RUN curl https://raw.githubusercontent.com/alttch/roboger/master/tests/test.py -o /usr/local/roboger-test.py
