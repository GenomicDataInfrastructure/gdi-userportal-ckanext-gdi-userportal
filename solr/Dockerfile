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

FROM eclipse-temurin:21-jdk@sha256:23cc5734ff46e776f51ce66eb9ee08444fd47caabec0a95b7eb6e94be2d3696d AS truststore
COPY --from=rhel-ca /etc/pki/ca-trust/extracted/java/cacerts /tmp/cacerts
# keytool output goes to a file first, so a keytool failure fails the build
# instead of being masked by the pipeline (sh has no pipefail).
RUN keytool -list -v -keystore /tmp/cacerts -storepass changeit > /tmp/list \
 && awk '/^Alias name: /{a=substr($0,13)} /^Owner: CN=(emSign ECC Root CA - G3|AAA Certificate Services),/{print a}' /tmp/list > /tmp/distrust \
 && while IFS= read -r a; do keytool -delete -keystore /tmp/cacerts -storepass changeit -alias "$a"; done < /tmp/distrust \
 && keytool -list -v -keystore /tmp/cacerts -storepass changeit > /tmp/list \
 && [ "$(grep -c '^Alias name: ' /tmp/list)" -ge 100 ] \
 && ! grep -qE "^Owner: CN=(emSign ECC Root CA - G3|AAA Certificate Services)," /tmp/list

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

# Create a CKAN configset by copying the default one
RUN cp -R $SOLR_CONFIG_DIR/_default $SOLR_CONFIG_DIR/ckan

# Update the schema
COPY ./schema.xml $SOLR_SCHEMA_FILE
RUN chmod 644 $SOLR_SCHEMA_FILE

USER solr

CMD ["sh", "-c", "solr-precreate ckan $SOLR_CONFIG_DIR/ckan"]
