# Only upstream Kea is compiled. The project hook is downloaded in the final image.
FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55 AS kea-build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential cmake ninja-build pkg-config python3-venv bison flex \
    ca-certificates libboost-dev libboost-system-dev liblog4cplus-dev \
    libssl-dev libpq-dev libmariadb-dev libmariadb-dev-compat \
    && rm -rf /var/lib/apt/lists/*
COPY scripts/requirements-quality.txt /tmp/requirements-quality.txt
RUN python3 -m venv /opt/tools && /opt/tools/bin/pip install \
    --require-hashes --only-binary=:all: -r /tmp/requirements-quality.txt
COPY scripts/build_kea.py scripts/kea-source.json /opt/builder/
ARG BUILD_JOBS=2
RUN PATH="/opt/tools/bin:$PATH" python3 /opt/builder/build_kea.py \
    --work-dir /opt/kea --jobs "$BUILD_JOBS"

FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
ENV DEBIAN_FRONTEND=noninteractive \
    LD_LIBRARY_PATH=/opt/kea/install/lib \
    PYTHONPATH=/opt/tests \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install --no-install-recommends -y \
    ca-certificates python3 binutils iproute2 libboost-system1.83.0 \
    liblog4cplus-2.0.5t64 libssl3t64 libpq5 libmariadb3 \
    postgresql-client mariadb-client \
    && rm -rf /var/lib/apt/lists/*
COPY --from=kea-build /opt/kea/install /opt/kea/install
COPY --from=kea-build /opt/kea/toolchain.txt /opt/kea/config.report /opt/kea/
RUN rm -rf /opt/kea/install/include /opt/kea/install/lib/pkgconfig \
    && find /opt/kea/install/sbin -type f \
       ! -name kea-dhcp4 ! -name kea-admin ! -name kea-lfc -delete \
    && find /opt/kea/install/lib/kea/hooks -type f \
       ! -name libdhcp_pgsql.so ! -name libdhcp_mysql.so -delete
COPY tests/docker/install_release.py /opt/install_release.py
RUN python3 /opt/install_release.py && dpkg-query -W > /opt/kea/runtime-packages.txt
COPY tests/control.py tests/smoke.py tests/dhcp.py /opt/tests/
COPY tests/docker/validate.py /opt/validate.py
WORKDIR /evidence
CMD ["python3", "/opt/validate.py"]
