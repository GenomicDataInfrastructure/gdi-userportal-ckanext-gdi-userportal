# SPDX-FileCopyrightText: 2024 PNED G.I.E.
#
# SPDX-License-Identifier: Apache-2.0

# Curated Java trust store (CVE-2026-91403, eMudhra/emSign distrust).
# solr:10.0.0-slim ships Temurin 25.0.4.1 (2026-08-18), whose root list still
# trusts emSign ECC Root CA - G3. Until a solr:10.0.x-slim tag with the October
# Temurin build is published, replace it with the patched RHEL store
# (ca-certificates from RHSA-2026:88459) and fail the build if either distrusted
# root is present. The Temurin stage is only used for keytool.
FROM registry.access.redhat.com/ubi9-minimal:1792742129 AS rhel-ca
RUN microdnf update -y ca-certificates && microdnf clean all

FROM eclipse-temurin:21.0.12_8-jdk@sha256:92a2a4d7a928d057e7bd999c418d66c26a34eb9a0442f3ab67721c3f88110b2d AS truststore
COPY --from=rhel-ca /etc/pki/ca-trust/extracted/java/cacerts /tmp/cacerts
# keytool output goes to a file first, so a keytool failure fails the build
# instead of being masked by the pipeline (sh has no pipefail).
RUN keytool -list -v -keystore /tmp/cacerts -storepass changeit > /tmp/list \
 && awk '/^Alias name: /{a=substr($0,13)} /^Owner: CN=(emSign ECC Root CA - G3|AAA Certificate Services),/{print a}' /tmp/list > /tmp/distrust \
 && while IFS= read -r a; do keytool -delete -keystore /tmp/cacerts -storepass changeit -alias "$a"; done < /tmp/distrust \
 && keytool -list -v -keystore /tmp/cacerts -storepass changeit > /tmp/list \
 && [ "$(grep -c '^Alias name: ' /tmp/list)" -ge 100 ] \
 && ! grep -qE "^Owner: CN=(emSign ECC Root CA - G3|AAA Certificate Services)," /tmp/list

# Fixed versions of the Jetty, Jackson, Netty and ZooKeeper jars bundled in Solr 10.0.0, downloaded from
# Maven Central and checked against the SHA-256 pinned in bundled-libs.txt. Stopgap until an official
# Solr release ships them.
FROM docker.io/solr:10.0.0-slim AS bundled-libs
USER root
COPY bundled-libs.txt /tmp/bundled-libs.txt
RUN set -eu; mkdir /libs; \
    grep -v -e '^#' -e '^$' /tmp/bundled-libs.txt | while read -r sha path dir old; do \
      curl -fsS --retry 3 -o "/libs/${path##*/}" "https://repo1.maven.org/maven2/$path"; \
      echo "$sha  /libs/${path##*/}" | sha256sum -c -; \
    done

FROM docker.io/solr:10.0.0-slim

EXPOSE 8983

ENV SOLR_CONFIG_DIR="/opt/solr/server/solr/configsets"
ENV SOLR_SCHEMA_FILE="$SOLR_CONFIG_DIR/ckan/conf/managed-schema"

USER root

# Replace the JRE trust store with the curated one and check that the JVM uses it
COPY --from=truststore --chmod=644 /tmp/cacerts $JAVA_HOME/lib/security/cacerts
RUN keytool -list -v -cacerts -storepass changeit > /tmp/cacerts.txt \
 && [ "$(grep -c '^Alias name: ' /tmp/cacerts.txt)" -ge 100 ] \
 && ! grep -qE "^Owner: CN=(emSign ECC Root CA - G3|AAA Certificate Services)," /tmp/cacerts.txt \
 && rm /tmp/cacerts.txt

# Remove gosu (a Go binary, built with go1.22.2 in solr:10.0.0-slim). Nothing uses it: the image runs
# as solr, Solr's scripts never call it, and upstream dropped it in Solr 9.11/10 (SOLR-17353); only the
# 10.0 image still installs it.
RUN dpkg --purge gosu && ! command -v gosu

# Swap each bundled jar for its fixed version (rm fails if Solr's layout changed), then fail the build
# if any jar of the replaced versions is left
COPY --from=bundled-libs /libs/ /tmp/bundled-libs/
COPY bundled-libs.txt /tmp/bundled-libs.txt
RUN set -eu; cd /opt/solr; \
    grep -v -e '^#' -e '^$' /tmp/bundled-libs.txt | while read -r sha path dir old; do \
      rm "$dir/$old"; \
      install -m 644 -o root -g root "/tmp/bundled-libs/${path##*/}" "$dir/"; \
    done; \
    rm -r /tmp/bundled-libs /tmp/bundled-libs.txt; \
    ! find -L /opt/solr -name '*.jar' | grep -E '/(jetty-[a-z0-9-]+-12\.0\.27|jackson-[a-z-]+-2\.20(\.0)?|netty-[a-z0-9-]+-4\.2\.6\.Final(-[a-z0-9_-]+)?|netty-tcnative-[a-z-]+-2\.0\.70\.Final|zookeeper(-jute)?-3\.9\.4)\.jar$'

# Create a CKAN configset by copying the default one
RUN cp -R $SOLR_CONFIG_DIR/_default $SOLR_CONFIG_DIR/ckan

# Update the schema
COPY ./schema.xml $SOLR_SCHEMA_FILE
RUN chmod 644 $SOLR_SCHEMA_FILE

USER solr

CMD ["sh", "-c", "solr-precreate ckan $SOLR_CONFIG_DIR/ckan"]
