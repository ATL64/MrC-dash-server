## Dash server for Biotech-MRC

Currently accessible here: http://35.242.239.52

This app is built with Dash, a Python framework to build elegant interactive dashboards for the web. 
We also use a template to create a Docker image that uses Flask, Nginx, and uWSGI to serve the application.

This app will basically take your question, scan the entire pubmed database of abstracts, and evaluate the question against a few chosen articles to return an answer.



## Dockerize your Dash app

Run locally:

1. Create Docker image
```
docker build -t my_dashboard .
```

2. Run app in container
```
docker run -p 8080:80 my_dashboard
```
This will run the app on http://localhost:8080/.

The base image used in the Dockerfile: https://hub.docker.com/r/tiangolo/uwsgi-nginx-flask/.


### CICD

- For every commit in a pull request, there will be a qa-machine available for 10 minutes after the push, accessible here http://34.107.37.64 

- When the PR is merged to master, CircleCi will replace the prod vm and point to the ip address http://35.242.239.52

### Manual Deployment

1. Tag your image (check you image id with ``docker image ls```)

```
docker tag f1d29a9739a2 eu.gcr.io/durable-catbird-204706/biotech_mrc_v1
```

2. Push to Google image repository

```
docker push eu.gcr.io/durable-catbird-204706/biotech_mrc_v1
```

3. Create VM in GCE with

- Zone: Frankfurt
- 1CPU, 3.75G
- Debian (default)
- Tick the "deploy a container image to this VM" option
- Paste the name of the image e.g
 
 ```eu.gcr.io/durable-catbird-204706/biotech_mrc_v1```

- Tick both the http and https traffic checkboxes
- Create the VM


### Debugging

If you deploy the app in prod or qa and is not behaving as expected,
 you can check the docker logs to see the output of dash.  To do this,
 
 1. SSH to the machine
 
 2. Run ````docker ps````

 3. Run ```docker logs your_docker_container_id```



