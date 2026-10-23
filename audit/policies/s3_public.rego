package planproof.deny

import rego.v1

# Deny planned S3 bucket ACLs that grant public access.
deny contains result if {
	some rc in input.plan.resource_changes
	rc.type == "aws_s3_bucket"
	some action in rc.change.actions
	action in {"create", "update"}
	acl := rc.change.after.acl
	acl in {"public-read", "public-read-write", "authenticated-read"}
	result := {
		"rule": "TF_S3_PUBLIC_ACL",
		"title": "S3 bucket ACL grants public access",
		"severity": "high",
		"resource": rc.address,
		"msg": sprintf("planned ACL %q on %s grants public access", [acl, rc.address]),
	}
}

# Deny planned S3 public-access-block settings that leave the bucket exposed.
deny contains result if {
	some rc in input.plan.resource_changes
	rc.type == "aws_s3_bucket_public_access_block"
	some action in rc.change.actions
	action in {"create", "update"}
	some field in {"block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets"}
	rc.change.after[field] == false
	result := {
		"rule": "TF_S3_PUBLIC_ACCESS_BLOCK_DISABLED",
		"title": "S3 public access block is disabled",
		"severity": "high",
		"resource": rc.address,
		"msg": sprintf("%s is false on %s", [field, rc.address]),
	}
}
