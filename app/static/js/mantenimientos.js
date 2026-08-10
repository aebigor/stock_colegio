const buscar = document.getElementById("buscar");

if (buscar) {

    buscar.addEventListener("keyup", function () {

        let valor = this.value.toLowerCase();

        let filas = document.querySelectorAll("#tabla tbody tr");

        filas.forEach(fila => {

            fila.style.display =
                fila.innerText.toLowerCase().includes(valor)
                    ? ""
                    : "none";

        });

    });

}