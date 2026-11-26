{{- define "chaos-agent.postgresql.fullname" -}}
{{- printf "%s-postgresql" .Release.Name -}}
{{- end -}}

{{- define "chaos-agent.postgresql.selectorLabels" -}}
app.kubernetes.io/name: postgresql
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "chaos-agent.postgresql.secretName" -}}
{{- if .Values.postgresql.auth.existingSecret -}}
{{- .Values.postgresql.auth.existingSecret -}}
{{- else -}}
{{- include "chaos-agent.postgresql.fullname" . -}}
{{- end -}}
{{- end -}}

{{- /* MCP servers. Called with (list $ $level), where $level is observe, probe or disrupt. */ -}}
{{- define "chaos-agent.mcp.fullname" -}}
{{- printf "%s-mcp-%s" (index . 0).Release.Name (index . 1) -}}
{{- end -}}

{{- define "chaos-agent.mcp.selectorLabels" -}}
app.kubernetes.io/name: mcp
app.kubernetes.io/instance: {{ (index . 0).Release.Name }}
app.kubernetes.io/component: {{ index . 1 }}
{{- end -}}

{{- /* The Kubernetes permissions of each level. A level with no rules gets no Role. */ -}}
{{- define "chaos-agent.mcp.rules" -}}
{{- if eq . "probe" }}
# Read a Service to check that a port is declared before sending traffic to it.
- apiGroups: [""]
  resources: [services]
  verbs: [get]
{{- end }}
{{- end -}}
