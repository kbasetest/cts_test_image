FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime

ARG RUN_USER=root

ADD ./tester.py /opt

RUN if [ "$RUN_USER" != "root" ]; then \
    useradd -u 65532 -r -s /bin/bash nonroot; \
    fi

USER ${RUN_USER}

ENTRYPOINT ["python", "/opt/tester.py"]
