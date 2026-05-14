(function () {
  "use strict";

  var fields = [
    { name: "cloud_init_user", label: "ciuser" },
    { name: "cloud_init_ssh_keys", label: "sshkeys" },
    { name: "cloud_init_user_data", label: "user-data" },
    { name: "cloud_init_network", label: "network" }
  ];

  function findField(name) {
    var selectors = [
      "#id_cf_" + name,
      "#id_" + name,
      "[name='cf_" + name + "']",
      "[name='" + name + "']",
      "[name='custom_field_data." + name + "']"
    ];
    for (var i = 0; i < selectors.length; i += 1) {
      var field = document.querySelector(selectors[i]);
      if (field) {
        return field;
      }
    }
    return null;
  }

  var inputs = fields
    .map(function (field) {
      return {
        name: field.name,
        label: field.label,
        input: findField(field.name)
      };
    })
    .filter(function (field) {
      return Boolean(field.input);
    });

  if (inputs.length === 0) {
    return;
  }

  function closestBlock(element) {
    return element.closest(".field, .form-group, .mb-3, tr") || element.parentNode;
  }

  var preview = document.getElementById("intent-cloud-init-preview");
  if (!preview) {
    preview = document.createElement("pre");
    preview.id = "intent-cloud-init-preview";
    preview.className = "border rounded p-2 bg-light text-body mt-2";
    var anchor = closestBlock(inputs[inputs.length - 1].input);
    anchor.parentNode.insertBefore(preview, anchor.nextSibling);
  }

  function valueOf(input) {
    if (input.type === "checkbox") {
      return input.checked ? "true" : "";
    }
    return (input.value || "").trim();
  }

  function render() {
    var lines = [];
    inputs.forEach(function (field) {
      var value = valueOf(field.input);
      if (value) {
        lines.push(field.label + ": " + value);
      }
    });
    preview.textContent = lines.length ? lines.join("\n") : "cloud-init: no fields set";
    preview.classList.toggle(
      "text-danger",
      preview.textContent.toLowerCase().indexOf("password:") !== -1
    );
  }

  inputs.forEach(function (field) {
    field.input.addEventListener("input", render);
    field.input.addEventListener("change", render);
  });
  render();
})();
