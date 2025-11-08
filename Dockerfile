FROM python:3.13

ADD ./tester.py /opt

ENTRYPOINT ["python", "/opt/tester.py"]
