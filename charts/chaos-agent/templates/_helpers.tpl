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