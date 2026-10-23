package planproof.deny

import rego.v1

# Surface every planned delete (including replacement deletes) as an explicit
# high-risk finding so destructive changes appear in evidence, not only in
# the plan summary badges.

deny contains result if {
	some rc in input.plan.resource_changes
	rc.mode != "data"
	"delete" in rc.change.actions
	result := {
		"rule": "TF_PLAN_DESTRUCTIVE_ACTION",
		"title": "Planned destructive action",
		"severity": "high",
		"resource": rc.address,
		"msg": sprintf("plan includes destructive action for %s: %v", [rc.address, rc.change.actions]),
	}
}
