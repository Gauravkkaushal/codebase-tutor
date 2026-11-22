import axios from "axios";

export default function Notes() {
  const load = async () => {
    const res = await axios.get(
      "http://localhost:5000/api/notes"
    );
    return res.data;
  };
  const add = async (text) => {
    await axios.post(`http://localhost:5000/api/notes/add`, { text });
  };
  return null;
}
