from wsgiref import headers
import pika
import time
import json 
import datetime
import os
import requests

sleepTime = 20
print(' [*] Sleeping for ', sleepTime, ' seconds.')
time.sleep(sleepTime)

print(' [*] Connecting to server ...')
address=os.environ['RABBIT']
connection = pika.BlockingConnection(pika.ConnectionParameters(host=address))
channel = connection.channel()
channel.queue_declare(queue='rpc_queue')

print(' [*] Waiting for messages.')

TIMEOUT="timeout"

# working function to read info in batches
def work(buffer, iterations, expire): 
    import hashlib
    output = hashlib.sha512(buffer).digest() 
    start = time.time()
    for i in range(int(iterations) - 1):
        print(time.time() - start, flush=True)
        # if there is timeout we stop the process
        if (time.time() - start > expire):
            return TIMEOUT
        output = hashlib.sha512(output).digest()
    print(output, flush=True)
    return output

# This function is called once a messafe is taken from the queue
def on_request(ch, method, props, body):
    timestamp = time.time()
    now = datetime.datetime.now()

    data = json.loads(body.decode("utf-8"))
    expire = float(data['expire'])
    output = work(data['payload'].encode("utf-8"), data['iterations'].encode("utf-8"), expire)
    
    created = float(data['created'][0])
    time_taken = timestamp - created
    headers= {'time':str(time_taken)}

    # if timeout we want to get the instance id and send it for scaling
    if output == TIMEOUT:
        instnace_id = requests.get("http://169.254.169.254/latest/meta-data/instance-id ")
        headers= {'instnace_id':instnace_id}
        output = b'TIMEOUT'
        
    ch.basic_publish(exchange='',
                     routing_key=props.reply_to,
                     properties=pika.BasicProperties(
                     correlation_id=props.correlation_id,
                     headers= headers),
                     body=output)
    ch.basic_ack(delivery_tag=method.delivery_tag)


channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='rpc_queue', on_message_callback=on_request)

print(" [x] Awaiting RPC requests")
channel.start_consuming()