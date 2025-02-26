
async function FastAPIConnectionTest(fastapiEndpoint) {
    let fastapi_docs_endpoint = `${fastapiEndpoint}/docs`

    try {
        const request_fastapi = await fetch(fastapi_docs_endpoint)
        console.log("request_fastapi", request_fastapi)
        if (request_fastapi.ok) {
            console.log("FastAPI OK")
            //onst response_fastapi = await request_fastapi.json()

            console.log("request_fastapi", request_fastapi)

            let statusBadgeFastAPI = document.getElementById('fastapi-connection-status')
            if (statusBadgeFastAPI) {
                statusBadgeFastAPI.className = "text-bg-green badge p-1"
                statusBadgeFastAPI.textContent = "Successful!"
            }
        }
    } catch (error) {
        let statusErrorBadgeFastAPI = document.getElementById('fastapi-connection-status')

        if (statusErrorBadgeFastAPI) {
            statusErrorBadgeFastAPI.className = "text-bg-red badge p-1"
            statusErrorBadgeFastAPI.textContent = "Connection Failed!"
        }
    }

}



async function NetboxAPIConnectionTest(fastapiEndpoint) {
    let netboxTestRoute = `${fastapiEndpoint}/netbox/status`
    
    try {
        const requestNetbox = await fetch(netboxTestRoute)
        const responseNetbox = await requestNetbox.json()

        console.log("requestNetbox", requestNetbox)
        if (requestNetbox.ok) {
            let statusBadgeNetbox = document.getElementById('netbox-connection-status')

            if (statusBadgeNetbox) {
                statusBadgeNetbox.className = "text-bg-green badge p-1"
                statusBadgeNetbox.textContent = "Successful!"
            }

            let netboxVersion = document.getElementById('netbox-version')

            if (netboxVersion) {
                netboxVersion.innerHTML = `<span class='badge text-bg-grey' title='Netbox Version'>
                    <strong>
                        <i class='mdi mdi-tag'></i>
                    </strong> ${responseNetbox["netbox-version"]}
                </span>`
            }

            let pythonVersion = document.getElementById('python-version')

            if (pythonVersion) {
                pythonVersion.innerHTML = `<span class='badge text-bg-grey' title='Python Version'>
                    <strong>
                        <i class='mdi mdi-tag'></i>
                    </strong> ${responseNetbox["python-version"]}
                </span>`
            }

            let djangoVersion = document.getElementById('django-version')
            if (djangoVersion) {
                djangoVersion.innerHTML = `<span class='badge text-bg-grey' title='Django Version'>
                    <strong>
                        <i class='mdi mdi-tag'></i>
                    </strong> ${responseNetbox["django-version"]}
                </span>`
            }

            let netboxPlugins = document.getElementById('netbox-plugins')
            if (netboxPlugins) {
                netboxPlugins.innerHTML = `<span class='badge text-bg-blue' title='Netbox Proxbox Version'>
                    <strong>
                        <i class='mdi mdi-tag'></i>
                    </strong> ${responseNetbox["plugins"]["netbox_proxbox"]}
                </span>`
            }
        }

        else {
            let statusErrorBadgeNetboxAPI = document.getElementById('netbox-connection-status')
            statusErrorBadgeNetboxAPI.className = "text-bg-red badge p-1"
            statusErrorBadgeNetboxAPI.textContent = "Connection Failed!"
        }
    } catch (error) {
        let statusErrorBadgeNetboxAPI = document.getElementById('netbox-connection-status')
        statusErrorBadgeNetboxAPI.className = "text-bg-red badge p-1"
        statusErrorBadgeNetboxAPI.textContent = "Connection Failed!"
    }


}


function getBody () {
    // Load 'getVersion()' function on HTML
    let body = document.getElementsByTagName("body")
    body = body[0]

    body.onload = getVersion
}

getBody()


async function getVersion() {
    let virtualMachinesDiv = document.getElementById('virtual-machines-div')
    virtualMachinesDiv.style.display = "none"

    // Test FastAPI Proxbox Backend Connection
    console.log("Testing FastAPI Connection...")
    FastAPIConnectionTest(fastapiEndpoint)

    console.log("Testing NetBox API Connection...")
    NetboxAPIConnectionTest(fastapiEndpoint)


    // Get Info from Proxmox and Add to GUI Page, like Connection Status and Error Messages
    let elemento = document.getElementsByClassName("proxmox_version")

    for (let item of elemento) {

        let td = item.getElementsByTagName("td")
        let th = item.getElementsByTagName("th")
        
        if (td[0].id) {
            let tdID = td[0].id
            
            const version_endpoint = `${fastapiEndpoint}/proxmox/version?source=netbox&list_all=false&plugin_name=netbox_proxbox&domain=${tdID}`
            const cluster_endpoint = `${fastapiEndpoint}/proxmox/sessions?source=netbox&list_all=false&plugin_name=netbox_proxbox&domain=${tdID}`
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


export { FastAPIConnectionTest, NetboxAPIConnectionTest, getVersion }