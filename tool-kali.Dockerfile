# Built only by an explicit `cyber tools install kali`, inside the guest.
FROM kalilinux/kali-rolling
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl jq git python3 ripgrep nmap sqlmap ffuf \
    && apt-get clean && find /var/lib/apt/lists -mindepth 1 -delete
WORKDIR /work
CMD ["bash"]
