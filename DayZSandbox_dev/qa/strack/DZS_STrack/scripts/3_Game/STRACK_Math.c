// S-track helpers. Math3D has QuatLerp (linear, enmath3d.c:397) and no slerp.
// Math.Exp is not in 1_core/proto/enmath.c; Exp() is a Taylor series.

class STRACK_Math
{
	static float Exp(float x)
	{
		float term;
		float sum;
		int n;
		if (x > 8.0)
		{
			x = 8.0;
		}
		if (x < -8.0)
		{
			x = -8.0;
		}
		term = 1.0;
		sum = 1.0;
		n = 1;
		while (n <= 20)
		{
			term = term * x / n;
			sum = sum + term;
			n = n + 1;
		}
		return sum;
	}

	static vector Cross(vector a, vector b)
	{
		return Vector(a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]);
	}

	static vector MulPoint(vector m[4], vector p)
	{
		return m[3] + m[0] * p[0] + m[1] * p[1] + m[2] * p[2];
	}

	static void Copy4(vector src[4], out vector dst[4])
	{
		dst[0] = src[0];
		dst[1] = src[1];
		dst[2] = src[2];
		dst[3] = src[3];
	}

	static string N(float v)
	{
		string s;
		s = v.ToString();
		s.Replace(",", ".");
		return s;
	}

	static string V(vector v)
	{
		return "[" + N(v[0]) + "," + N(v[1]) + "," + N(v[2]) + "]";
	}

	static string FrameBmp(int frame)
	{
		string n;
		n = frame.ToString();
		while (n.Length() < 6)
		{
			n = "0" + n;
		}
		return "f" + n + ".bmp";
	}

	static void Look(vector from, vector to, vector up, out vector mat[4])
	{
		vector dir;
		vector upN;
		float len;
		float dot;
		dir = to - from;
		len = dir.Length();
		if (len < 0.000001)
		{
			dir = Vector(0, 0, 1);
		}
		else
		{
			dir = dir * (1.0 / len);
		}
		upN = up;
		len = upN.Length();
		if (len < 0.000001)
		{
			upN = Vector(0, 1, 0);
		}
		else
		{
			upN = upN * (1.0 / len);
		}
		dot = vector.Dot(dir, upN);
		if (dot > 0.98 || dot < -0.98)
		{
			upN = Vector(0, 0, 1);
		}
		Math3D.DirectionAndUpMatrix(dir, upN, mat);
		mat[3] = from;
	}

	// Positive degrees: optical axis rotates toward camera +X (right).
	static void YawRight(vector mat[4], float deg, out vector o[4])
	{
		float c;
		float s;
		vector x;
		vector z;
		vector nx;
		vector nz;
		c = Math.Cos(deg * Math.DEG2RAD);
		s = Math.Sin(deg * Math.DEG2RAD);
		x = mat[0];
		z = mat[2];
		nz = z * c + x * s;
		nx = x * c - z * s;
		nz.Normalize();
		nx.Normalize();
		o[0] = nx;
		o[2] = nz;
		o[1] = Cross(nz, nx);
		o[1].Normalize();
		o[3] = mat[3];
	}

	// Positive degrees about the optical axis (+Z), x toward y.
	static void RollOptic(vector mat[4], float deg, out vector o[4])
	{
		float c;
		float s;
		vector x;
		vector y;
		c = Math.Cos(deg * Math.DEG2RAD);
		s = Math.Sin(deg * Math.DEG2RAD);
		x = mat[0];
		y = mat[1];
		o[0] = x * c + y * s;
		o[1] = y * c - x * s;
		o[0].Normalize();
		o[1].Normalize();
		o[2] = mat[2];
		o[3] = mat[3];
	}

	// Short-arc slerp. q and -q are the same rotation (flip when dot < 0).
	static void Slerp(vector a[4], vector b[4], float t, out vector o[4])
	{
		vector ra[3];
		vector rb[3];
		vector r[3];
		float qa[4];
		float qb[4];
		float q[4];
		float dot;
		float theta;
		float st;
		float w1;
		float w2;
		float len;
		ra[0] = a[0];
		ra[1] = a[1];
		ra[2] = a[2];
		rb[0] = b[0];
		rb[1] = b[1];
		rb[2] = b[2];
		Math3D.MatrixToQuat(ra, qa);
		Math3D.MatrixToQuat(rb, qb);
		dot = qa[0] * qb[0] + qa[1] * qb[1] + qa[2] * qb[2] + qa[3] * qb[3];
		if (dot < 0.0)
		{
			qb[0] = -qb[0];
			qb[1] = -qb[1];
			qb[2] = -qb[2];
			qb[3] = -qb[3];
			dot = -dot;
		}
		if (dot > 1.0)
		{
			dot = 1.0;
		}
		if (dot > 0.9995)
		{
			q[0] = qa[0] + (qb[0] - qa[0]) * t;
			q[1] = qa[1] + (qb[1] - qa[1]) * t;
			q[2] = qa[2] + (qb[2] - qa[2]) * t;
			q[3] = qa[3] + (qb[3] - qa[3]) * t;
		}
		else
		{
			theta = Math.Acos(dot);
			st = Math.Sin(theta);
			w1 = Math.Sin((1.0 - t) * theta) / st;
			w2 = Math.Sin(t * theta) / st;
			q[0] = qa[0] * w1 + qb[0] * w2;
			q[1] = qa[1] * w1 + qb[1] * w2;
			q[2] = qa[2] * w1 + qb[2] * w2;
			q[3] = qa[3] * w1 + qb[3] * w2;
		}
		len = Math.Sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
		if (len > 0.0000001)
		{
			q[0] = q[0] / len;
			q[1] = q[1] / len;
			q[2] = q[2] / len;
			q[3] = q[3] / len;
		}
		Math3D.QuatToMatrix(q, r);
		o[0] = r[0];
		o[1] = r[1];
		o[2] = r[2];
		o[3] = a[3];
	}
};
