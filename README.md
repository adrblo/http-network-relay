# HTTP Network Relay over WebSockets

|<video src="https://github.com/user-attachments/assets/7ddd48a1-e5d8-4b76-9efc-499b9e63cdad" />|
|-|
|Server, client and SSH proxy command in action|

Three binaries: `server`, `client`, and `ssh-proxy-command`.

The server is supposed to be run on a machine with a public IP address.
Ideally the server should be run behind a reverse proxy that terminates TLS, such that the clients can trust the server's identity.

The client is supposed to be run on a machine that needs to access the server's network.
The client will establish a WebSocket connection to the server.

The `ssh-proxy-command` is a script that can be used as a ProxyCommand in an SSH configuration file.
It will establish a WebSocket connection to the server and forward the SSH connection over the WebSocket connection.
It can also be used as a general purpose proxy command for other protocols.

## Server

Expects environment variable `HTTP_NETWORK_RELAY_CREDENTIALS_FILE` to point to a json file with the following structure:

```json
{
  "clients": {
    "client-name": "THIS-IS-THE-SECRET-THE-CLIENT-USES-TO-AUTHENTICATE-WITH-THE-SERVER"
  },
  "proxy_users": [
    "THIS-IS-A-TOKEN-THAT-PROXY-USERS-USE-TO-AUTHENTICATE-WITH-THE-SERVER"
  ]
}
```

## Client

The client will establish a WebSocket connection to the server.

Usage: `client --server_url <server_url> --client-name <client-name> --client-secret <client-secret>`

It will connect to the server using the `--server_url` command line argument.
The default value is `ws://127.0.0.1:8000/ws_for_clients`.
This can be set using the environment variable `HTTP_NETWORK_RELAY_SERVER_URL`.

The client will identify itself to the server using the `client-name` command line argument.
The `client-name` is a unique identifier for the client and is used to authenticate the client with the server, as well as identify the client to the server and users.
The client will authenticate with the server using the `client-secret` command line argument.
Both can be set using environment variables `HTTP_NETWORK_RELAY_CLIENT_NAME` and `HTTP_NETWORK_RELAY_CLIENT_SECRET`.
For the client to be able to authenticate with the server, the server must have the client's name and secret in its credentials file.

## SSH Proxy Command

The `ssh-proxy-command` script can be used as a ProxyCommand in an SSH configuration file.

Usage: `ssh-proxy-command <target_host_identifier> <target_ip> <target_port> <protocol> --server_url <server_url> --secret-key <secret_key>`

The `target_host_identifier` is the `client-name` of the client that connects to the server.
The `target_ip` and `target_port` are the IP address and port of the connection that the client wants to establish.
The `protocol` is the protocol that the client wants to use (e.g. 'udp' or 'tcp'). Currently only 'tcp' is supported.

The `server_url` is the URL of the server that the client wants to connect to.
It can also be set using the environment variable `HTTP_NETWORK_RELAY_SERVER_URL`.

The proxy command also takes a `secret-key` argument.
This is the secret key that the client uses to authenticate with the server.
It can also be set using the environment variable `HTTP_NETWORK_RELAY_SECRET_KEY`.

The `ssh-proxy-command` script will establish a WebSocket connection to the server and forward its stdin and stdout to the server.
The server will forward the data to the client, which will then establish the connection to the target connection details.
