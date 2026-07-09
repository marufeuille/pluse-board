terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # backend: まずは local state（terraform.tfstate は .gitignore 済み）。
  # GCS backend へ移行する練習は terraform/README.md を参照。
}
