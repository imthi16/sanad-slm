# Sovereign GPU server — vLLM V1 engine serving the AWQ (compressed-tensors) checkpoint (§6.1).
# The model dir is a read-only PVC synced from MinIO by an initContainer; this image never
# fetches from the hub (offline env is baked in).
FROM vllm/vllm-openai:v0.9.0

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    VLLM_NO_USAGE_STATS=1 \
    DO_NOT_TRACK=1

COPY entrypoint.sh /entrypoint.sh
# the base image runs as root; drop to a fixed uid for k8s runAsNonRoot
RUN chmod +x /entrypoint.sh && useradd -u 10001 -m vllm
USER 10001

ENTRYPOINT ["/entrypoint.sh"]
