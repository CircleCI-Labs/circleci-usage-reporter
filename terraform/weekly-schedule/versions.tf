terraform {
  required_version = ">= 1.5.0"

  required_providers {
    circleci = {
      source  = "CircleCI-Public/circleci"
      version = "~> 0.5.0"
    }
  }
}

# Auth: CIRCLE_TOKEN (context circle-token-cci-labs in CI).
provider "circleci" {}
