## Kind insatlltion on ubuntu

```bash
KIND_VERSION=v0.32.0

cd /tmp
curl -fLO "https://github.com/kubernetes-sigs/kind/releases/download/${KIND_VERSION}/kind-linux-amd64"
curl -fLO "https://github.com/kubernetes-sigs/kind/releases/download/${KIND_VERSION}/kind-linux-amd64.sha256sum"

sha256sum -c kind-linux-amd64.sha256sum
sudo install -m 0755 kind-linux-amd64 /usr/local/bin/kind

kind version

```