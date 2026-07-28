const sidebar=document.getElementById("sidebar");

const button=document.getElementById("toggleSidebar");

button.addEventListener("click",()=>{

    sidebar.classList.toggle("collapsed");

});