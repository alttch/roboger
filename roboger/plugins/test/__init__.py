import roboger.core


def send(config, msg, subject, *args, **kwargs):
    roboger.core.logger.info(
        f'Sending message with config {config} and subject {subject}')
