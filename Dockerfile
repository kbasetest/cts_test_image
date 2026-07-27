FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime AS base

ADD ./tester.py /opt

FROM base AS nonroot-base

RUN useradd -u 65532 -r -s /bin/bash nonroot
USER nonroot

FROM nonroot-base AS nonroot

ENTRYPOINT ["python", "/opt/tester.py"]

FROM nonroot-base AS script

ENTRYPOINT ["/input_files/.__script__"]

FROM base AS root

ENTRYPOINT ["python", "/opt/tester.py"]
