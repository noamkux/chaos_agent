"""Manual check of the checks catalog: loading, selection by kind and focus, and the rendered prompt."""
import catalog

checks = catalog.load_catalog()
print("loaded:", len(checks))

all_kinds = catalog.select_checks(checks, {"Deployment", "Service"})
print("Deployment + Service:", len(all_kinds))

no_service = catalog.select_checks(checks, {"Deployment"})
print("Deployment only:", len(no_service))

exposure = catalog.select_checks(checks, {"Deployment", "Service"}, {"areas": ["exposure"]})
print("focus areas=exposure:", sorted(exposure))

prompt = catalog.render_index(all_kinds)
print("prompt length (chars):", len(prompt))
print()
print(prompt)
