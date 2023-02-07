# fluentd-elasticsearch

## Description

Fluentd is an open-source data collector for a unified logging layer. Fluentd allows you to unify 
data collection and consumption for better use and understanding of data. This fluentd charm 
is specifically built to forward Magma logs to elasticsearch.

## Usage

```bash
juju deploy fluentd-elasticsearch --trust --channel edge \
--config domain="example.com" \
--config elasticsearch-url="yourelasticsearch:9200" 
```

## Config

### Config options

- **domain**:  Domain for self-signed certificate generation.
- **elasticsearch-url**: ElasticSearch URL (example: orc8r-elasticsearch:9200).
- **fluentd-chunk-limit-size**: The size limit of the received chunk. If the chunk size is larger 
than this value, the received chunk is dropped. Defaults to 2M.
- **fluentd-queue-limit-length**: The limit of the chunk queue length. If the chunk queue length 
is larger than this value, the received chunk is dropped. Defaults to 8.

```bash
juju config fluentd <CONFIG OPTION>=<VALUE>
```

> The elasticsearch configuration will be modeled using juju relations once there is a kubernetes
> charm for elasticsearch.

## Relations

### Requires

- **fluentd-certs**: Relation that provides certificates for Fluentd.

## OCI Images

Default: gcr.io/google-containers/fluentd-elasticsearch:v2.4.0
