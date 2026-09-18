# Storage integrations

To import from a **private** bucket, Pinecone needs read access to it. You grant that once by creating a **storage integration** in the Pinecone console; it produces an **Integration ID** you pass to `start_import` (`--integration-id` for `scripts/run_import.py`).

> **Public buckets need no integration.** If the bucket/container is publicly readable, skip this entirely and start the import without an Integration ID.

## Where the Integration ID lives

After you create an integration, its ID appears on the **Storage integrations** page of the Pinecone console:
<https://app.pinecone.io/organizations/-/projects/-/storage>

Copy that value — it's what you pass at import time.

## Amazon S3

Pinecone reads your bucket by assuming an IAM role you create with read permissions scoped to the import prefix.

1. In your AWS account, create an IAM role/policy granting read access (`s3:GetObject`, `s3:ListBucket`) to the bucket and prefix you'll import from.
2. Configure the trust relationship so Pinecone's account can assume the role (the console's S3 integration flow shows the exact principal/external ID to trust).
3. In the Pinecone console → **Storage integrations** → add an Amazon S3 integration, supplying the role ARN.
4. Copy the resulting Integration ID.

Full step-by-step (current principal and external ID values): <https://docs.pinecone.io/guides/operations/integrations/integrate-with-amazon-s3>

## Google Cloud Storage

Pinecone reads your bucket via a service account you authorize.

1. Grant read access (e.g. `roles/storage.objectViewer`) on the bucket to the service account the console's GCS integration flow specifies.
2. In the Pinecone console → **Storage integrations** → add a Google Cloud Storage integration.
3. Copy the resulting Integration ID.

Full step-by-step: <https://docs.pinecone.io/guides/operations/integrations/integrate-with-google-cloud-storage>

## Azure Blob Storage

Pinecone reads your container via the access you configure in the Azure integration flow.

1. In the Pinecone console → **Storage integrations** → add an Azure Blob Storage integration and follow the prompts to authorize read access to your container.
2. Copy the resulting Integration ID.

Full step-by-step: <https://docs.pinecone.io/guides/operations/integrations/integrate-with-azure-blob-storage>

## Using the Integration ID

Once you have it, pass it when starting the import:

```bash
uv run --env-file .env scripts/run_import.py \
  --index my-index \
  --uri s3://my-private-bucket/import_data/ \
  --integration-id a12b3d4c-47d2-492c-a97a-dd98c8dbefde
```

Or in code: `index.start_import(uri=..., integration_id="a12b3d4c-...")`. Omit it for public buckets.
