# A better Kubernetes Secrets with AWS Secrets Manager

## Motivation

Kubernetes Secrets let you store and manage sensitive information, such as passwords, authentication tokens, and ssh keys. However, a lot of production-grade systems avoid using Kubernetes Secrets for storing secrets as it does not include an option for strong encryptions but only `base64` encodings. AWS ECS has out of the box integration with AWS Secrets Manager but not the same case with AWS EKS.

This was the motivation for creating this implementation which consumes a secret from AWS Secrets Manager and injects it in our main containers.

## How it works

It contains a simple python based [init-container](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/) for fetching secrets from AWS Secrets Manager to Kubernetes pods. It fetches the provided key from AWS Secrets Manager and store it in pods' volume as `emptyDir` at a specified location, so that the main containers can use them in the application.

![How it works](images/HowItWorks.jpg?raw=true "How it works")

## Usage

The init-secret container requires these env variables to work :

- `SECRET_FILE_PATH` - Specifies the location in emptyDir volume to store the credentials. For example - `/secret/secret.env`
- `SM_DB` - The key of the secrets manager to be fetched. For example - `demo-database-secret` which would contain our secrets as key value pairs.
- `AWS_REGION` - The AWS region where the secrets have been put in the secrets manager. For example - `ap-southeast-1`

**NOTE**

- The name of the env should be in format `*SSM_<.env-prefix>*`. For ex: `SSM_DB` or `SSM_SECRETS`

- All the keys fetched from secret manager will be converted to uppercase and prefixed with `env-prefix`. For example - if the env var for the init-container is `SM_DB` then the key for `password` would be `DB_PASSWORD`.
  
- The volume `secret-volume` should be an `emptyDir` and mounted to both init-container and main containers.

- Make sure the pods have access to the AWS Secret Manager, this implementation assumes that the required permissions have been granted to the [EC2 Instance Profile](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html) (add permissions to [Amazon EKS node IAM role](https://docs.aws.amazon.com/eks/latest/userguide/worker_node_IAM_role.html) in case of EKS) to nodes where pods would be spinning up, instead of using AWS Access Keys and Secret Keys. An example policy for the minimal permissions required can be found in [examples/secrets-policy.json](examples/secrets-policy.json).

## AWS Secrets Manager

Create a secret in AWS Secret Manager like below, follow [this AWS guide](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_create-basic-secret.html) for creating a basic secret.

![AWS Secrets Manager](images/AWSSecretsManager.JPG?raw=true "AWS Secrets Manager")



## Kubernetes implementation

- Make sure you are able to connect to the kubernetes cluster:
  
```console
➜  ~ kubectl get nodes
NAME                                                STATUS   ROLES    AGE   VERSION
ip-192-168-36-74.ap-southeast-1.compute.internal    Ready    <none>   72m   v1.16.13-eks-2ba888
ip-192-168-48-236.ap-southeast-1.compute.internal   Ready    <none>   72m   v1.16.13-eks-2ba888
ip-192-168-73-240.ap-southeast-1.compute.internal   Ready    <none>   71m   v1.16.13-eks-2ba888
```

- A basic kubernetes deployment yaml looks like below and can be found in [examples/k8s-deployment.yaml](examples/k8s-deployment.yaml):
  
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: secret-manager
  labels:
    app: my-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      volumes:
      - name: secret-volume
        emptyDir: {}
      initContainers:
      - name: init-secret
        image: clouddrove/aws-secret:1.0
        imagePullPolicy: Always
        command: ["python"]
        args:
          - "secret.py"
        env:
        - name: SECRET_FILE_PATH
          value: "/secret/secret.env"
        - name: SSM_DB
          value: "demo-database-secret"
        - name: AWS_REGION
          value: "ap-southeast-1"
        volumeMounts:
          - mountPath: /secret
            name: secret-volume
      containers:
      - name: main-app
        image: busybox
        imagePullPolicy: Always
        command: ["/bin/sh", "-c"]
        # Run your application command after sourcing env file or use the env file to your convenience
        args:
          - "source /secret/secret.env && while true; do echo '\n\n$DB_PASSWORD = '$DB_PASSWORD; echo '\nContents of secret.env file:'; cat /secret/secret.env;  sleep 2; done"
        env:
          - name: SECRET_FILE_PATH
            value: "/secret/secret.env"
        volumeMounts:
          - mountPath: /secret
            name: secret-volume
```

- Apply the yaml to create a deployment:

```console
➜  ~ kubectl apply -f examples/k8s-deployment.yaml
deployment.apps/secret-manager created
```

- Check the status of the created pods, here `Init:0/1` indicates that zero of the one Init Containers has completed successfully:

```console
➜  ~ kubectl get pods
NAME                              READY   STATUS     RESTARTS   AGE
secret-manager-6685f778c7-lmk9g   0/1     Init:0/1   0          2s
secret-manager-6685f778c7-vggxn   0/1     Init:0/1   0          2s
```

- After a while if the init-container runs successfully pods goes in `PodInitializing` state which indicates our main app container is being created now:

```console
➜  ~ kubectl get pods
NAME                              READY   STATUS            RESTARTS   AGE
secret-manager-6685f778c7-lmk9g   0/1     PodInitializing   0          5s
secret-manager-6685f778c7-vggxn   0/1     PodInitializing   0          5s
```

- As soon as the main app container is up and running, the pod status becomes `Running` :

```console
➜  ~ kubectl get pods
NAME                              READY   STATUS    RESTARTS   AGE
secret-manager-6685f778c7-lmk9g   1/1     Running   0          10s
secret-manager-6685f778c7-vggxn   1/1     Running   0          10s
```

- To check the logs of our init-secret container, simply append `-c init-secret` to the `kubectl logs` command :

```console
➜  ~ kubectl logs secret-manager-6685f778c7-lmk9g -c init-secret
Running init container script
Saving demo-database-secret secrets to /secret/secret.env
Done fetching secrets demo-database-secret
Exiting init container script
```

- To check the logs of the main container, use the following command :
  
```console
➜  ~ kubectl logs secret-manager-6685f778c7-lmk9g

$DB_PASSWORD = supersecretpassword

Contents of secret.env file:
DB_USERNAME='demo'
DB_PASSWORD='supersecretpassword'
DB_ENGINE='mysql'
DB_HOST='127.0.0.1'
DB_PORT='3306'
DB_DBNAME='demo'
```

- As we can see, the secrets have been injected properly in our main container which can easily be used as required, without having to create any other kubernetes resources. The values of the secrets in `secret.env` is exactly the same as we have created in our [AWS Secret Manager](#aws-secrets-manager).

- To cleanup the deployment we have created :

```console
➜  ~ kubectl delete -f examples/k8s-deployment.yaml
deployment.apps "secret-manager" deleted
```