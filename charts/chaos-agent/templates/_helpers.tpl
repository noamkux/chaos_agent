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
{{- else if eq . "disrupt" }}
# Change any object in the namespace, custom resources included. Reads come from the built-in view
# ClusterRole (no Secrets). What may never be changed is enforced by the disrupt-guard admission policy.
- apiGroups: ["*"]
  resources: ["*"]
  verbs: [patch, update]
- apiGroups: [""]
  resources: [pods]
  verbs: [delete]
# Evict pods from a node in these namespaces, as kubectl drain does (PodDisruptionBudgets respected).
- apiGroups: [""]
  resources: [pods/eviction]
  verbs: [create]
{{- end }}
{{- end -}}


{{- /* CEL: the pod spec at path (string) did not change in any field that would run other code or gain
privileges, compared to the same path in oldObject. Called with (list "object.spec" "oldObject.spec"). */ -}}
{{- define "chaos-agent.mcp.podGuard" -}}
{{- $new := index . 0 -}}{{- $old := index . 1 -}}
{{ $new }}.containers.map(c, c.image) == {{ $old }}.containers.map(c, c.image)
&& {{ $new }}.containers.map(c, c.?command.orValue([])) == {{ $old }}.containers.map(c, c.?command.orValue([]))
&& {{ $new }}.containers.map(c, c.?args.orValue([])) == {{ $old }}.containers.map(c, c.?args.orValue([]))
&& {{ $new }}.containers.map(c, c.?securityContext.orValue({})) == {{ $old }}.containers.map(c, c.?securityContext.orValue({}))
&& {{ $new }}.?initContainers.orValue([]) == {{ $old }}.?initContainers.orValue([])
&& {{ $new }}.?serviceAccountName.orValue("") == {{ $old }}.?serviceAccountName.orValue("")
&& {{ $new }}.?automountServiceAccountToken.orValue(true) == {{ $old }}.?automountServiceAccountToken.orValue(true)
&& {{ $new }}.?hostNetwork.orValue(false) == {{ $old }}.?hostNetwork.orValue(false)
&& {{ $new }}.?hostPID.orValue(false) == {{ $old }}.?hostPID.orValue(false)
&& {{ $new }}.?hostIPC.orValue(false) == {{ $old }}.?hostIPC.orValue(false)
&& {{ $new }}.?securityContext.orValue({}) == {{ $old }}.?securityContext.orValue({})
&& {{ $new }}.?volumes.orValue([]) == {{ $old }}.?volumes.orValue([])
{{- end -}}
