#!/usr/bin/env bash
# Component registry reader. Data remains in manifests/components.tsv.
# The caller defines deblestia_manifest before sourcing this file.

deblestia_component_field() {
    # shellcheck disable=SC2154 # The caller defines this before sourcing the reader.
    awk -F '\t' -v id="$1" -v field="$2" \
        '$0 !~ /^#/ && $1 == id {print $field; exit}' "$deblestia_manifest"
}

deblestia_components_for_profile() {
    awk -F '\t' -v profile="$1" \
        '$0 !~ /^#/ && ("," $4 ",") ~ ("," profile ",") {print $1}' \
        "$deblestia_manifest"
}
