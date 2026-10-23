package planproof.deny

import rego.v1

# Deny planned IAM policies that grant Allow on Resource "*".

policy_doc(pol) := doc if {
	is_string(pol)
	json.unmarshal(pol, doc)
}

statements(doc) := stmts if {
	is_array(doc.Statement)
	stmts := doc.Statement
}

statements(doc) := [doc.Statement] if {
	is_object(doc.Statement)
}

wildcard_resource(stmt) if stmt.Resource == "*"

wildcard_resource(stmt) if {
	is_array(stmt.Resource)
	"*" in stmt.Resource
}

deny contains result if {
	some rc in input.plan.resource_changes
	rc.type in {"aws_iam_policy", "aws_iam_role_policy", "aws_iam_user_policy", "aws_iam_group_policy"}
	some action in rc.change.actions
	action in {"create", "update"}
	doc := policy_doc(rc.change.after.policy)
	some stmt in statements(doc)
	stmt.Effect == "Allow"
	wildcard_resource(stmt)
	result := {
		"rule": "TF_IAM_WILDCARD_RESOURCE",
		"title": "IAM policy allows wildcard resource",
		"severity": "high",
		"resource": rc.address,
		"msg": sprintf("planned policy on %s allows Action on Resource *", [rc.address]),
	}
}
