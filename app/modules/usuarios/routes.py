from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.security import hash_password
from app.core.templates import templates
from app.modules.auth.dependencies import get_current_user, require_super_admin
from app.modules.auth.models import Rol, Usuario

router = APIRouter(
    prefix="/usuarios",
    tags=["Usuarios"],
    dependencies=[Depends(get_current_user)],
)


def _roles_disponibles(db: Session):
    return (
        db.query(Rol)
        .filter(Rol.estado.is_(True), Rol.nombre.in_([
            "Super Admin", "Administrador de Medios", "Administrador de Logística"
        ]))
        .order_by(Rol.nombre)
        .all()
    )


def _area_para_rol(nombre_rol: str) -> str:
    if nombre_rol == "Super Admin":
        return "Todas"
    if nombre_rol == "Administrador de Logística":
        return "Logística"
    return "Medios"


@router.get("/")
def index(
    request: Request,
    actor: Usuario = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    usuarios = (
        db.query(Usuario)
        .options(joinedload(Usuario.rol))
        .order_by(Usuario.nombre, Usuario.apellido)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="usuarios/index.html",
        context={"title": "Usuarios", "usuarios": usuarios},
    )


@router.get("/crear")
def crear_formulario(
    request: Request,
    actor: Usuario = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    roles = _roles_disponibles(db)
    return templates.TemplateResponse(
        request=request,
        name="usuarios/crear.html",
        context={"title": "Registrar usuario", "roles": roles},
    )


@router.post("/crear")
def crear_usuario(
    nombre: str = Form(...),
    apellido: str = Form(...),
    correo: str = Form(...),
    usuario: str = Form(...),
    password: str = Form(...),
    rol_id: int = Form(...),
    actor: Usuario = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    nombre_usuario = usuario.strip().lower()
    correo_usuario = correo.strip().lower()
    if len(password) < 10:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 10 caracteres.")
    if db.query(Usuario).filter(
        (Usuario.usuario == nombre_usuario) | (Usuario.correo == correo_usuario)
    ).first():
        raise HTTPException(status_code=400, detail="El usuario o correo ya está registrado.")

    rol = db.query(Rol).filter(Rol.id == rol_id, Rol.estado.is_(True)).first()
    if rol is None or rol.nombre not in {
        "Super Admin", "Administrador de Medios", "Administrador de Logística"
    }:
        raise HTTPException(status_code=400, detail="Selecciona un rol válido.")

    area = _area_para_rol(rol.nombre)

    nuevo = Usuario(
        nombre=nombre.strip(),
        apellido=apellido.strip(),
        correo=correo_usuario,
        usuario=nombre_usuario,
        password=hash_password(password),
        estado=True,
        rol_id=rol.id,
        area=area,
    )
    db.add(nuevo)
    db.commit()
    return RedirectResponse(url="/usuarios", status_code=303)


@router.get("/{usuario_id}/editar")
def editar_usuario_formulario(
    usuario_id: int,
    request: Request,
    actor: Usuario = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    usuario = db.query(Usuario).options(joinedload(Usuario.rol)).filter(Usuario.id == usuario_id).first()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return templates.TemplateResponse(
        request=request,
        name="usuarios/editar.html",
        context={
            "title": "Editar usuario",
            "usuario_editado": usuario,
            "roles": _roles_disponibles(db),
            "es_propio_usuario": usuario.id == actor.id,
        },
    )


@router.post("/{usuario_id}/editar")
def actualizar_usuario(
    usuario_id: int,
    nombre: str = Form(...),
    apellido: str = Form(...),
    correo: str = Form(...),
    usuario: str = Form(...),
    rol_id: int = Form(...),
    password: str = Form(""),
    actor: Usuario = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    user = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    nombre_usuario = usuario.strip().lower()
    correo_usuario = correo.strip().lower()
    if len(nombre_usuario) < 3:
        raise HTTPException(status_code=400, detail="El nombre de usuario debe tener al menos 3 caracteres.")
    if db.query(Usuario).filter(
        Usuario.id != usuario_id,
        (Usuario.usuario == nombre_usuario) | (Usuario.correo == correo_usuario),
    ).first():
        raise HTTPException(status_code=400, detail="El usuario o correo ya está registrado por otra cuenta.")

    rol = db.query(Rol).filter(Rol.id == rol_id, Rol.estado.is_(True)).first()
    if rol is None or rol.nombre not in {
        "Super Admin", "Administrador de Medios", "Administrador de Logística"
    }:
        raise HTTPException(status_code=400, detail="Selecciona un rol válido.")
    if user.id == actor.id and rol.id != user.rol_id:
        raise HTTPException(status_code=400, detail="No puedes cambiar tu propio rol de Super Admin.")
    if password and len(password) < 10:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 10 caracteres.")

    user.nombre = nombre.strip()
    user.apellido = apellido.strip()
    user.correo = correo_usuario
    user.usuario = nombre_usuario
    user.rol_id = rol.id
    user.area = _area_para_rol(rol.nombre)
    if password:
        user.password = hash_password(password)
    db.commit()
    return RedirectResponse(url="/usuarios", status_code=303)


@router.post("/{usuario_id}/estado")
def cambiar_estado_usuario(
    usuario_id: int,
    actor: Usuario = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    user = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if user.id == actor.id:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta.")
    user.estado = not user.estado
    db.commit()
    return RedirectResponse(url="/usuarios", status_code=303)
