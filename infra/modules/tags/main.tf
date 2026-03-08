locals {
  base_tags = {
    environment = var.environment
    project     = var.project
    managed_by  = "terraform"
    owner       = var.owner
    component   = var.component
  }

  # Drop blank-value entries so resources don't carry empty tag keys.
  filtered_base = {
    for k, v in local.base_tags : k => v if v != ""
  }

  tags = merge(local.filtered_base, var.additional_tags)
}
