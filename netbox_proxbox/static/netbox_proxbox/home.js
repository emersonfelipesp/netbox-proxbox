/*
This script works, but is not being used as there's not official support
to link external script on head element to plugins.
*/

/*
const uvicorn_host = document.getElementById("uvicorn-host")
const uvicorn_port = document.getElementById("uvicorn-port")

console.log("uvicorn_host", uvicorn_host)
console.log("uvicorn_port", uvicorn_port)


const fastapi_endpoint = `http://${uvicorn_host}:${uvicorn_port}`
const websocket_endpoint = `ws://${uvicorn_host}:${uvicorn_port}/ws`

var ws = new WebSocket(websocket_endpoint);
ws.onmessage = function(event) {
    // Add WebSockets Messages came from FasstAPI backend on GUI

    var messages = document.getElementById('messages')
    var message = document.createElement('li')

    message.style.lineHeight = '170%'

    message.innerHTML = event.data
    messages.appendChild(message)

    var test = document.getElementById('scrollable-div')
    test.scrollTop = test.scrollHeight

};

ws.onerror = function(error) {
    console.log("WebSocket error observed: ", error);

    fullUpdateButton = document.getElementById('full-update-button')
    fullUpdateButton.className = "btn btn-red"

    fullUpdateMessage = document.getElementById('full-update-error-message')
    fullUpdateMessage.className = "text-red"

    let errorMessage = `
        <p align=center>
            <strong>WebSocket</strong> communication failed with <strong>${error.currentTarget.url}</strong>
            <br>The most probably cause is <strong>Proxbox Backend not running</strong> properly.
        </p>`

    fullUpdateMessage.innerHTML = errorMessage
    

    let statusBadgeError = document.getElementById('fastapi-connection-status')
    statusBadgeError.className = "text-bg-red badge p-1"
    statusBadgeError.textContent = "Connection Failed!"

    let statusErrorMessage = document.getElementById('fastapi-connection-error')
    statusErrorMessage.className = "text-bg-red p-2"
    statusErrorMessage.innerHTML = errorMessage
}

function sendMessage(event) {
    // Send Websocket Message
    ws.send("Start")
    event.preventDefault()
}

async function FastAPIConnectionTest(fastapi_endpoint) {
    let fastapi_docs_endpoint = `${fastapi_endpoint}/docs`

    const request_fastapi = await fetch(fastapi_docs_endpoint)
    console.log("request_fastapi", request_fastapi)
    if (request_fastapi.ok) {
        console.log("FastAPI OK")
        //onst response_fastapi = await request_fastapi.json()

        console.log("request_fastapi", request_fastapi)

        statusBadgeFastAPI = document.getElementById('fastapi-connection-status')
        statusBadgeFastAPI.className = "text-bg-green badge p-1"
        statusBadgeFastAPI.textContent = "Successful!"
        
    }

}


function getBody () {
    // Load 'getVersion()' function on HTML
    body = document.getElementsByTagName("body")
    body = body[0]

    body.onload = getVersion
}



getBody()

async function getVersion() {
    // Test FastAPI Proxbox Backend Connection
    console.log("1")
    FastAPIConnectionTest(fastapi_endpoint)
    console.log("2")

    // Get Info from Proxmox and Add to GUI Page, like Connection Status and Error Messages
    let elemento = document.getElementsByClassName("proxmox_version")

    for (let item of elemento) {

        let td = item.getElementsByTagName("td")
        let th = item.getElementsByTagName("th")
        
        if (td[0].id) {
            let tdID = td[0].id
            
            const version_endpoint = `${fastapi_endpoint}/proxmox/version?source=netbox&list_all=false&plugin_name=netbox_proxbox&domain=${tdID}`
            const cluster_endpoint = `${fastapi_endpoint}/proxmox/sessions?source=netbox&list_all=false&plugin_name=netbox_proxbox&domain=${tdID}`
            const endpoints = [version_endpoint, cluster_endpoint]
            
            let apiResponses = []

            if (endpoints) {
                for (let endpoint of endpoints){
                    try {
                        const request = await fetch(endpoint)
                        const response = await request.json()
                        apiResponses.push(response[0])

                        if (request.ok && response[0] && response[0].domain) {
                            let statusBadge = document.getElementById(`proxmox-connection-status-${response[0].domain}`)
                            
                            if (statusBadge) {
                                statusBadge.className = "text-bg-green badge p-1"
                                statusBadge.textContent = "Successful!"
                            }
                        }

                        if (request.status === 400) {
                            
                            let errorStatusBadge = document.getElementsByClassName("proxmox-connection-check")

                            let connectionError = document.getElementById(`proxmox-connection-error-${tdID}`)
                            let connectionErrorFilledMessage = document.getElementById(`proxmox-filled-message-${tdID}`)

                            if (!connectionErrorFilledMessage) {
                                connectionError.className = "text-bg-red p-2"
                                connectionError.innerHTML = `<p id="proxmox-filled-message-${tdID}"><strong>Message: </strong>${response.message}<br><strong>Detail: </strong>${response.message}<br><strong>Python Exception: </strong>${response.python_exception}</p>`
                            }

                            for (let item of errorStatusBadge) {

                                if (item.id.includes(`${tdID}`)) {
                                    console.log("ID FOUND.", item.id)
                                    item.className = "text-bg-red badge p-1"
                                    item.textContent = "Connection Failed!"
                                }
                            }
                        }

                    } catch (err) {
                        // If Connection Fails with Proxmox Cluster, continue trying to connect with other Proxmox Cluster Nodes configured.
                        continue
                    }
                }
            }

            if (apiResponses) {
                if (apiResponses[0]) {
                    for (let value in apiResponses[0]) {
                        // Add 'Proxmox Version' and 'Proxmox RepoID' to Proxmox Cluster Card Fields
                        // Response from FastAPI /proxmox/version
                        if (th[0].textContent === 'Proxmox Version') {
                            td[0].innerHTML = `<span class='badge text-bg-grey' title='Proxmox Version'><strong><i class='mdi mdi-tag'></i></strong> ${apiResponses[0][value].version}</span>`
                        }
                        if (th[0].textContent === 'Proxmox RepoID') {
                            td[0].innerHTML = `<span class='badge text-bg-grey' title='Proxmox RepoID'>${apiResponses[0][value].repoid}</span>`
                        }
                    }
                }

                if (apiResponses[1]) {

                    for (let value in apiResponses[1]) {
                        // Add 'Proxmox Cluster Name' and 'Proxmox Cluster Mode' to Proxmox Cluster Card Fields
                        // Response from FastAPI /proxmox/sessions
                        if (th[0].textContent === 'Proxmox Cluster Name') {
                            td[0].innerHTML = `<strong>${apiResponses[1].name}</strong>`
                        }

                        if (th[0].textContent === 'Proxmox Cluster Mode') {

                            let mode = apiResponses[1].mode
                            if ( mode === "standalone" ) { mode = "<span class='badge text-bg-blue' title='Standalone Mode'><strong><i class='mdi mdi-server'></i></strong> Standalone (Single Node)</span>" }
                            if ( mode === "cluster" ) { mode = "<span class='badge text-bg-purple' title='Cluster Mode'><strong><i class='mdi mdi-server'></i></strong> Cluster (Multiple Nodes)</span>" } 
                            td[0].innerHTML = `${mode}`
                        }
                    }
                }
            }

        }
    }
}
*/