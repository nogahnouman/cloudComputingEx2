######################################
## INITIALIZNG BEFORE PYTHON SCRIPT ##
######################################

## Create a VPC with DNS hostname enabled
AWS_VPC_ID=$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 --query Vpc.VpcId --output text)
echo $AWS_VPC_ID
aws ec2 modify-vpc-attribute --vpc-id $AWS_VPC_ID --enable-dns-hostnames "{\"Value\":true}"

# Create two public subnets
AWS_SUBNET_PUBLIC_ONE_ID=$(aws ec2 create-subnet --vpc-id $AWS_VPC_ID --cidr-block 10.0.1.0/24 --availability-zone us-east-1a --query Subnet.SubnetId --output text)
AWS_SUBNET_PUBLIC_TWO_ID=$(aws ec2 create-subnet --vpc-id $AWS_VPC_ID --cidr-block 10.0.2.0/24 --availability-zone us-east-1b --query Subnet.SubnetId --output text)


aws ec2 modify-subnet-attribute --subnet-id $AWS_SUBNET_PUBLIC_ONE_ID --map-public-ip-on-launch
aws ec2 modify-subnet-attribute --subnet-id $AWS_SUBNET_PUBLIC_TWO_ID --map-public-ip-on-launch

## Create an Internet Gateway
AWS_INTERNET_GATEWAY_ID=$(aws ec2 create-internet-gateway --query InternetGateway.InternetGatewayId --output text)
aws ec2 attach-internet-gateway --vpc-id $AWS_VPC_ID --internet-gateway-id $AWS_INTERNET_GATEWAY_ID

## Create a route table
AWS_CUSTOM_ROUTE_TABLE_ID=$(aws ec2 create-route-table --vpc-id $AWS_VPC_ID --query RouteTable.RouteTableId --output text)
aws ec2 create-route --route-table $AWS_CUSTOM_ROUTE_TABLE_ID --destination-cidr-block 0.0.0.0/0 --gateway-id $AWS_INTERNET_GATEWAY_ID

## Associate the public subnet with route table
AWS_ROUTE_TABLE_ASSOID_ONE=$(aws ec2 associate-route-table --subnet-id $AWS_SUBNET_PUBLIC_ONE_ID --route-table-id $AWS_CUSTOM_ROUTE_TABLE_ID --query AssociationId --output text)
AWS_ROUTE_TABLE_ASSOID_TWO=$(aws ec2 associate-route-table --subnet-id $AWS_SUBNET_PUBLIC_TWO_ID --route-table-id $AWS_CUSTOM_ROUTE_TABLE_ID --query AssociationId --output text)

# Create a security group
GROUP_ID=$(aws ec2 create-security-group --vpc-id $AWS_VPC_ID --group-name myvpc-security-group-4 --description 'my non default vpc' --output text)

echo $AWS_VPC_ID
echo $AWS_SUBNET_PUBLIC_TWO_ID
echo $AWS_SUBNET_PUBLIC_ONE_ID
echo $GROUP_ID

## Create security group ingress rules
aws ec2 authorize-security-group-ingress --group-id $GROUP_ID --ip-permissions IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges='[{CidrIp=0.0.0.0/0,Description="Allow SSH"}]'
aws ec2 authorize-security-group-ingress --group-id $GROUP_ID --ip-permissions IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges='[{CidrIp=0.0.0.0/0,Description="Allow HTTP"}]'
aws ec2 authorize-security-group-ingress --group-id $GROUP_ID --protocol tcp --port 5672 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $GROUP_ID --protocol tcp --port 15672 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $GROUP_ID --protocol tcp --port 4369 --cidr 0.0.0.0/0

python3 deploy_lb.py $GROUP_ID $AWS_SUBNET_PUBLIC_ONE_ID $AWS_SUBNET_PUBLIC_TWO_ID $AWS_VPC_ID