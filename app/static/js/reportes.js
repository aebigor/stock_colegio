new Chart(

document.getElementById("estadoChart"),

{

type:"doughnut",

data:{

labels:[

"Disponibles",

"Prestados",

"Mantenimiento",

"Baja"

],

datasets:[{

data:[

estados.disponibles,

estados.prestados,

estados.mantenimiento,

estados.baja

]

}]

}

}

);



new Chart(

document.getElementById("categoriaChart"),

{

type:"bar",

data:{

labels:categorias.map(x=>x.nombre),

datasets:[{

label:"Cantidad",

data:categorias.map(x=>x.cantidad)

}]

},

options:{

responsive:true,

plugins:{

legend:{

display:false

}

}

}

}

);