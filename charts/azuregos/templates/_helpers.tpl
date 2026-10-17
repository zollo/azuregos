{{- define "azuregos.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "azuregos.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "azuregos.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "azuregos.labels" -}}
helm.sh/chart: {{ include "azuregos.chart" . }}
app.kubernetes.io/name: {{ include "azuregos.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* Selector labels for one component: include "azuregos.selectorLabels" (list . "backend") */}}
{{- define "azuregos.selectorLabels" -}}
{{- $root := index . 0 -}}
app.kubernetes.io/name: {{ include "azuregos.name" $root }}
app.kubernetes.io/instance: {{ $root.Release.Name }}
app.kubernetes.io/component: {{ index . 1 }}
{{- end }}

{{- define "azuregos.tag" -}}
{{- .Values.image.tag | default .Chart.AppVersion | default "latest" }}
{{- end }}

{{- define "azuregos.backendImage" -}}
{{- printf "%s:%s" .Values.image.backend (include "azuregos.tag" .) }}
{{- end }}

{{- define "azuregos.frontendImage" -}}
{{- printf "%s:%s" .Values.image.frontend (include "azuregos.tag" .) }}
{{- end }}

{{- define "azuregos.secretName" -}}
{{- .Values.existingSecret | default (printf "%s-secrets" (include "azuregos.fullname" .)) }}
{{- end }}

{{- define "azuregos.postgresHost" -}}
{{- if .Values.postgresql.enabled }}
{{- printf "%s-postgres" (include "azuregos.fullname" .) }}
{{- else }}
{{- required "externalDatabase.host is required when postgresql.enabled is false" .Values.externalDatabase.host }}
{{- end }}
{{- end }}

{{- define "azuregos.postgresPort" -}}
{{- if .Values.postgresql.enabled }}5432{{ else }}{{ .Values.externalDatabase.port }}{{ end }}
{{- end }}

{{- define "azuregos.postgresUser" -}}
{{- if .Values.postgresql.enabled }}{{ .Values.postgresql.user }}{{ else }}{{ .Values.externalDatabase.user }}{{ end }}
{{- end }}

{{- define "azuregos.postgresDatabase" -}}
{{- if .Values.postgresql.enabled }}{{ .Values.postgresql.database }}{{ else }}{{ .Values.externalDatabase.database }}{{ end }}
{{- end }}

{{- define "azuregos.redisUrl" -}}
{{- if .Values.redis.enabled }}
{{- printf "redis://%s-redis:6379/0" (include "azuregos.fullname" .) }}
{{- else }}
{{- required "externalRedis.url is required when redis.enabled is false" .Values.externalRedis.url }}
{{- end }}
{{- end }}

{{/* envFrom shared by the backend, the migration init container and the worker */}}
{{- define "azuregos.envFrom" -}}
- configMapRef:
    name: {{ include "azuregos.fullname" . }}-config
- secretRef:
    name: {{ include "azuregos.secretName" . }}
{{- end }}

{{/* Restart pods when the chart-managed config or secret changes */}}
{{- define "azuregos.configChecksum" -}}
checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
{{- if not .Values.existingSecret }}
checksum/secret: {{ include (print $.Template.BasePath "/secret.yaml") . | sha256sum }}
{{- end }}
{{- end }}
