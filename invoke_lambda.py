import json
import boto3

FUNCTION_NAME = "HelloFunction"
REGION = "us-east-1"


def main():
    client = boto3.client("lambda", region_name=REGION)
    event = {"name": "Ozymandias"}
    response = client.invoke(
        FunctionName=FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(event).encode(),
    )
    payload = response["Payload"].read()
    try:
        print(json.loads(payload))
    except Exception:
        print(payload)


if __name__ == "__main__":
    main()


