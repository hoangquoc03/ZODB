import "./App.css";
import React, { useEffect, useState } from "react";
import axios from "axios";

export default function App() {
  const [people, setPeople] = useState([]);
  const [editId, setEditId] = useState(null);
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [showForm, setShowForm] = useState(false);
  const loadPeople = async () => {
    try {
      const res = await axios.get("http://127.0.0.1:5000/people");
      console.log("API trả về:", res.data);
      setPeople(res.data);
    } catch (err) {
      console.error("Lỗi khi gọi API:", err);
    }
  };

  useEffect(() => {
    loadPeople();
  }, []);

  const deletePerson = async (id) => {
    await axios.delete(`http://127.0.0.1:5000/people/${id}`);
    loadPeople();
  };
  const startEdit = (p) => {
    setEditId(p.id);
    setName(p.name);
    setAge(p.age);
    setShowForm(true);
  };
  const addPerson = async () => {
    if (!name || !age) return alert("Nhập đủ thông tin");
    await axios.post("http://127.0.0.1:5000/people", {
      name,
      age: parseInt(age),
    });
    setName("");
    setAge("");
    loadPeople();
  };

  const updatePerson = async () => {
    if (!editId) return;
    await axios.put(`http://127.0.0.1:5000/people/${editId}`, {
      name,
      age: parseInt(age),
    });
    setEditId(null);
    setName("");
    setAge("");
    loadPeople();
  };
  const openAddForm = () => {
    setEditId(null);
    setName("");
    setAge("");
    setShowForm(true);
  };

  const closeForm = () => {
    setEditId(null);
    setName("");
    setAge("");
    setShowForm(false);
  };

  return (
    <div className="app-container">
      <nav className="navigator">
        <button>Danh sách nhân viên</button>
        <button>Danh sách khách hàng</button>
      </nav>

      <div className="content">
        <h2> Danh sách nhân viên</h2>
        <button className="btn-add" onClick={openAddForm}>
          Thêm nhân viên
        </button>
        {people.length === 0 ? (
          <p>Chưa có dữ liệu trong ZODB</p>
        ) : (
          <table className="people-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Tên</th>
                <th>Tuổi</th>
                <th>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.id} className="tr">
                  <td>{p.id}</td>
                  <td>{p.name}</td>
                  <td>{p.age}</td>
                  <td>
                    <button
                      onClick={() => deletePerson(p.id)}
                      className="btn-delete"
                    >
                      Xóa
                    </button>
                    <button onClick={() => startEdit(p)} className="btn-edit">
                      Sửa
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {showForm && (
          <div className="modal-overlay">
            <div className="modal">
              <h2>{editId ? "Cập nhật nhân viên" : "Thêm nhân viên"}</h2>
              <input
                placeholder="Tên"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <input
                placeholder="Tuổi"
                type="number"
                value={age}
                onChange={(e) => setAge(e.target.value)}
              />
              <div className="modal-actions">
                {editId ? (
                  <button onClick={updatePerson} className="btn-save">
                    Cập nhật
                  </button>
                ) : (
                  <button onClick={addPerson} className="btn-save">
                    Thêm
                  </button>
                )}
                <button onClick={closeForm} className="btn-cancel">
                  Hủy
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
